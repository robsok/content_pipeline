# core/imap_poll.py
from __future__ import annotations

import imaplib
import os
import re
from datetime import datetime
from typing import Optional, Tuple

import email
from email.message import Message
from email import policy
from email.utils import parseaddr


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.getenv(name)
    return v if v is not None else default


def _allowed_senders() -> set[str]:
    raw = _env("REVIEW_ALLOWED_FROM", "") or ""
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


def _connect() -> imaplib.IMAP4_SSL:
    host = _env("IMAP_HOST")
    port_str = _env("IMAP_PORT", "993")
    user = _env("IMAP_USER")
    pwd = _env("IMAP_PASSWORD")
    folder = _env("IMAP_FOLDER", "INBOX") or "INBOX"

    if not (host and port_str and user and pwd):
        raise RuntimeError("IMAP not configured: need IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_PASSWORD")

    port = int(port_str)
    m = imaplib.IMAP4_SSL(host, port)
    m.login(user, pwd)
    typ, _ = m.select(folder)
    if typ != "OK":
        raise RuntimeError(f"Could not select folder {folder!r}")
    return m


def _extract_raw_bytes(msg_data: list) -> Optional[bytes]:
    """
    imaplib.fetch() often returns a list like:
      [(b'1 (RFC822 {1234}', b'...raw bytes...'), b')']
    We want the bytes in the tuple's second element.
    """
    for part in msg_data:
        if isinstance(part, tuple):
            maybe = part[1]
            if isinstance(maybe, (bytes, bytearray)):
                return bytes(maybe)
    return None


def _get_plain_text(msg: Message) -> str:
    """
    Try the modern API first (policy=default): Message.get_content() for text/plain.
    Fallback to get_payload(decode=True).
    """
    body_text = ""

    if msg.is_multipart():
        for part in msg.walk():
            try:
                if part.get_content_type() == "text/plain":
                    # Preferred: get_content() (handles charset)
                    try:
                        content = part.get_content()  # type: ignore[attr-defined]
                        if isinstance(content, str):
                            return content
                    except Exception:
                        pass

                    payload = part.get_payload(decode=True)
                    if isinstance(payload, (bytes, bytearray)):
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            return payload.decode(charset, errors="ignore")
                        except Exception:
                            return payload.decode("utf-8", errors="ignore")
                    elif isinstance(payload, str):
                        return payload
            except Exception:
                continue
        return body_text

    # Single-part
    try:
        content = msg.get_content()  # type: ignore[attr-defined]
        if isinstance(content, str):
            return content
    except Exception:
        pass

    payload = msg.get_payload(decode=True)
    if isinstance(payload, (bytes, bytearray)):
        charset = msg.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="ignore")
        except Exception:
            return payload.decode("utf-8", errors="ignore")
    if isinstance(payload, str):
        return payload

    return body_text


def find_latest_selection(run_token: str, date_str: Optional[str] = None) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    Returns (selection_line, email_uid, from_addr) or (None, None, None).

    We search by ASCII-safe BODY token "run <run_token>" so Unicode subjects won't break IMAP SEARCH.
    """
    allowed = _allowed_senders()
    date_str = date_str or datetime.now().strftime("%Y-%m-%d")
    token = f"run {run_token}"

    m = _connect()
    try:
        # Search unseen first, then all, using BODY token
        for criteria in [f'(UNSEEN BODY "{token}")', f'(BODY "{token}")']:
            typ, data = m.search(None, criteria)
            if typ != "OK" or not data or not data[0]:
                continue

            try:
                candidates = [int(x) for x in data[0].split()]
            except Exception:
                candidates = []

            candidates.sort(reverse=True)  # newest first

            for uid in candidates:
                typ_f, msg_data = m.fetch(str(uid), "(RFC822)")
                if typ_f != "OK" or not msg_data:
                    continue

                raw_bytes = _extract_raw_bytes(msg_data)
                if raw_bytes is None:
                    continue

                # Use modern policy for better parsing and get_content()
                msg = email.message_from_bytes(raw_bytes, policy=policy.default)

                # From header
                from_header = msg.get("From", "")
                _, addr = parseaddr(from_header)
                from_addr = (addr or "").lower()
                if allowed and from_addr not in allowed:
                    continue

                body_text = _get_plain_text(msg)

                # Find first line that looks like a selection
                for line in body_text.splitlines():
                    s = line.strip()
                    if s and re.fullmatch(r"[\d,\-\s]+", s):
                        return (s, uid, from_addr)

        return (None, None, None)
    finally:
        try:
            m.close()
        except Exception:
            pass
        try:
            m.logout()
        except Exception:
            pass
