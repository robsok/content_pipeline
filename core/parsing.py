import time
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urlparse

def clean_html(html: str) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return " ".join(text.split())

def parse_feed(url: str) -> list[dict]:
    feed = feedparser.parse(url)
    feed_title = getattr(feed.feed, "title", urlparse(url).path)
    items = []
    for e in feed.entries:
        title = getattr(e, "title", "").strip()
        link = getattr(e, "link", "").strip()
        summary_raw = getattr(e, "summary", getattr(e, "description", ""))
        summary = clean_html(summary_raw)
        ts = 0
        if getattr(e, "published_parsed", None):
            ts = int(time.mktime(e.published_parsed))
        elif getattr(e, "updated_parsed", None):
            ts = int(time.mktime(e.updated_parsed))
        items.append({
            "feed": feed_title,
            "title": title,
            "link": link,
            "summary": summary,
            "published_ts": ts,
        })
    return items

def fetch_items(feed_urls: list[str]) -> list[dict]:
    all_items = []
    for u in feed_urls:
        all_items.extend(parse_feed(u))
    # De-duplicate by link
    by_key = {}
    for it in all_items:
        key = it["link"] or (it["feed"] + "|" + it["title"])
        old = by_key.get(key)
        if not old or it["published_ts"] > old["published_ts"]:
            by_key[key] = it
    items = list(by_key.values())
    items.sort(key=lambda x: x["published_ts"], reverse=True)
    return items

