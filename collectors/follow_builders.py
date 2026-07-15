#!/usr/bin/env python3
"""Follow Builders public X, blog, and podcast feeds."""
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import extract_keywords, get_json, mk_signal, write_raw  # noqa: E402


SOURCE = "follow_builders"
RAW_BASE = os.environ.get(
    "NEED_RADAR_FOLLOW_BUILDERS_BASE",
    "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main",
)
BUILDER_MARKERS = (
    "build", "built", "ship", "launch", "product", "feature", "workflow", "agent",
    "model", "design", "experiment", "customer", "revenue", "growth", "open source",
    "architecture", "code", "tool", "automation", "prompt", "dataset", "developer",
    "api", "inference", "training", "startup", "founder",
)
PROMO_MARKERS = ("giveaway", "tell us what you love", "win $", "coupon", "limited offer")


def compact_title(text, limit=96):
    clean = re.sub(r"\s+", " ", text or "").strip()
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def _engagement_score(popularity, text=""):
    score = 48 + min(24, math.log10(max(0, popularity) + 1) * 8)
    if len(text) >= 160:
        score += 5
    if text.lstrip().startswith("@"):
        score -= 10
    return round(max(40, min(82, score)), 1)


def parse_x_feed(payload):
    signals = []
    for builder_rank, builder in enumerate(payload.get("x") or [], start=1):
        name = (builder.get("name") or builder.get("handle") or "Builder").strip()
        handle = (builder.get("handle") or "").strip()
        for item_rank, tweet in enumerate(builder.get("tweets") or [], start=1):
            text = (tweet.get("text") or "").strip()
            url = (tweet.get("url") or "").strip()
            # Link-only replies do not deserve attention merely because their
            # author is curated.
            visible_words = re.sub(r"https?://\S+|@\w+", " ", text).strip()
            if not text or not url or len(visible_words) < 18:
                continue
            lowered = text.lower()
            if any(marker in lowered for marker in PROMO_MARKERS):
                continue
            if not any(marker in lowered for marker in BUILDER_MARKERS):
                continue
            popularity = sum(int(tweet.get(k) or 0) for k in ("likes", "retweets", "replies"))
            signals.append(mk_signal(
                id=f"{SOURCE}-x-{tweet.get('id') or url}",
                source=SOURCE,
                source_label="Follow Builders",
                region="海外",
                lang="en",
                title=compact_title(text),
                text=text[:1200],
                url=url,
                popularity=popularity,
                comments=int(tweet.get("replies") or 0),
                created_at=tweet.get("createdAt") or "",
                signal_type="trend",
                keywords=extract_keywords(text, "en"),
                content_kind="builder",
                category="builder-x",
                author=name,
                handle=handle,
                author_bio=builder.get("bio") or "",
                attribution="Follow Builders",
                external_score=_engagement_score(popularity, text),
                source_rank=builder_rank * 100 + item_rank,
            ))
    return signals


def parse_blog_feed(payload):
    signals = []
    for rank, post in enumerate(payload.get("blogs") or [], start=1):
        title = (post.get("title") or "").strip()
        url = (post.get("url") or "").strip()
        if not title or not url:
            continue
        content = (post.get("description") or post.get("content") or "").strip()
        name = (post.get("name") or "Official Blog").strip()
        signals.append(mk_signal(
            id=f"{SOURCE}-blog-{url}",
            source=SOURCE,
            source_label="Follow Builders",
            region="海外",
            lang="en",
            title=title,
            text=content[:1600],
            url=url,
            popularity=0,
            comments=0,
            created_at=post.get("publishedAt") or "",
            signal_type="trend",
            keywords=extract_keywords(f"{title} {content}", "en"),
            content_kind="builder",
            category="builder-blog",
            author=post.get("author") or name,
            external_source=name,
            attribution="Follow Builders",
            external_score=68,
            source_rank=rank,
        ))
    return signals


def parse_podcast_feed(payload):
    signals = []
    for rank, episode in enumerate(payload.get("podcasts") or [], start=1):
        title = (episode.get("title") or "").strip()
        url = (episode.get("url") or "").strip()
        if not title or not url:
            continue
        transcript = (episode.get("transcript") or episode.get("description") or "").strip()
        podcast = (episode.get("name") or "Podcast").strip()
        signals.append(mk_signal(
            id=f"{SOURCE}-podcast-{episode.get('guid') or url}",
            source=SOURCE,
            source_label="Follow Builders",
            region="海外",
            lang="en",
            title=title,
            text=transcript[:1600],
            url=url,
            popularity=0,
            comments=0,
            created_at=episode.get("publishedAt") or "",
            signal_type="trend",
            keywords=extract_keywords(f"{title} {transcript[:500]}", "en"),
            content_kind="builder",
            category="builder-podcast",
            author=podcast,
            external_source=podcast,
            attribution="Follow Builders",
            external_score=66,
            source_rank=rank,
        ))
    return signals


def run():
    signals = []
    errors = []
    feeds = (
        ("feed-x.json", parse_x_feed),
        ("feed-blogs.json", parse_blog_feed),
        ("feed-podcasts.json", parse_podcast_feed),
    )
    for filename, parser in feeds:
        try:
            signals.extend(parser(get_json(f"{RAW_BASE}/{filename}", timeout=20, retries=1)))
        except Exception as exc:
            errors.append(f"{filename}: {exc}")
    if errors:
        print("[follow_builders] " + " | ".join(errors))
    write_raw(SOURCE, signals)


if __name__ == "__main__":
    run()
