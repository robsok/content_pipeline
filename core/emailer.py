# core/emailer.py
import os, smtplib, mimetypes, ssl, traceback
from email.message import EmailMessage
from pathlib import Path

def send_email(subject: str, body_text: str, attachments: list[str] | None = None) -> None:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pwd  = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_TLS", "true").lower() in ("1","true","yes")
    use_ssl = os.getenv("SMTP_SSL", "false").lower() in ("1","true","yes")
    sender = os.getenv("EMAIL_FROM", user or "")
    recipients = [r.strip() for r in os.getenv("EMAIL_TO","").split(",") if r.strip()]

    if not (host and port and user and pwd and sender and recipients):
        raise RuntimeError("Email not configured: need SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM/TO")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body_text)

    for path in (attachments or []):
        p = Path(path)
        if not p.exists():
            continue
        ctype, _ = mimetypes.guess_type(str(p))
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name)

    try:
        if use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context) as s:
                s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                if use_tls:
                    s.starttls(context=ssl.create_default_context())
                s.login(user, pwd)
                s.send_message(msg)
    except Exception:
        # Print full traceback so it's obvious why it failed
        print("[EMAIL] Failed to send email. Traceback:")
        traceback.print_exc()
        raise
