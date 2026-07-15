import unittest

from collectors.github_trending import parse_trending_html
from collectors.producthunt import parse_feed


PRODUCTHUNT_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>tag:www.producthunt.com,2005:Post/1182460</id>
    <published>2026-06-27T08:17:01-07:00</published>
    <updated>2026-06-28T05:43:27-07:00</updated>
    <link rel="alternate" type="text/html" href="https://www.producthunt.com/products/lyto" />
    <title>Lyto</title>
    <content type="html"><![CDATA[
      <p>"One AI agent across your browser, tools, and messages "</p>
      <p><a href="https://www.producthunt.com/products/lyto#discussion">Discussion</a> | <a href="https://example.com">Link</a></p>
    ]]></content>
  </entry>
</feed>
"""


GITHUB_TRENDING_SAMPLE = """
<article class="Box-row">
  <h2 class="h3 lh-condensed">
    <a href="/simplex-chat/simplex-chat" class="Link">
      simplex-chat / simplex-chat
    </a>
  </h2>
  <p class="col-9 color-fg-muted my-1 pr-4">
    SimpleX - the most private and secure chat and application platform.
  </p>
  <span itemprop="programmingLanguage">Haskell</span>
  <a href="/simplex-chat/simplex-chat/stargazers"> 9,876 </a>
  <span class="d-inline-block float-sm-right"> 123 stars today </span>
</article>
"""


class HighSignalCollectorTest(unittest.TestCase):
    def test_producthunt_feed_entry_becomes_commercial_launch_signal(self):
        signals = parse_feed(PRODUCTHUNT_SAMPLE.encode("utf-8"))

        self.assertEqual(len(signals), 1)
        sig = signals[0]
        self.assertEqual(sig["source"], "producthunt")
        self.assertEqual(sig["source_label"], "Product Hunt")
        self.assertEqual(sig["signal_type"], "launch")
        self.assertEqual(sig["url"], "https://www.producthunt.com/products/lyto")
        self.assertIn("One AI agent", sig["text"])
        self.assertNotIn("Discussion", sig["text"])
        self.assertNotIn("Link", sig["text"])

    def test_github_trending_article_becomes_trend_signal(self):
        signals = parse_trending_html(GITHUB_TRENDING_SAMPLE.encode("utf-8"))

        self.assertEqual(len(signals), 1)
        sig = signals[0]
        self.assertEqual(sig["source"], "github_trending")
        self.assertEqual(sig["source_label"], "GitHub Trending")
        self.assertEqual(sig["signal_type"], "trend")
        self.assertEqual(sig["title"], "simplex-chat/simplex-chat")
        self.assertEqual(sig["popularity"], 123)
        self.assertIn("Haskell", sig["keywords"])


if __name__ == "__main__":
    unittest.main()
