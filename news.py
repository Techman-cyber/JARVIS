"""
Fetches a single top headline for the startup briefing - same key-free
Google News RSS approach server.py already uses for the web dashboard's
/api/news, just exposed as a plain function so main.py/voice_live.py can
use it too without needing Flask running.
"""

import xml.etree.ElementTree as ET
import requests


def get_top_headline(country: str = "US", lang: str = "en-US") -> str:
    """Returns a short 'Title — Source' string, or '' if it couldn't be
    fetched for any reason (no internet, feed hiccup, etc.) - callers should
    treat that as 'skip the news line', not an error worth surfacing."""
    ceid = f"{country}:{lang.split('-')[0]}"
    url = f"https://news.google.com/rss?hl={lang}&gl={country}&ceid={ceid}"

    try:
        resp = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        item = root.find(".//item")
        if item is None:
            return ""

        title = (item.findtext("title") or "").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""

        if not title:
            return ""
        return f"{title} — {source}" if source else title
    except Exception:
        return ""


if __name__ == "__main__":
    print(get_top_headline() or "Couldn't fetch a headline.")
