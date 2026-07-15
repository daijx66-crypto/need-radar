import unittest


class AttentionCollectorTest(unittest.TestCase):
    def test_aihot_selected_item_becomes_shift_signal(self):
        from collectors.aihot import parse_items

        signals = parse_items({
            "items": [{
                "id": "a1",
                "title": "新模型发布",
                "summary": "面向本地 Agent 的新能力。",
                "url": "https://example.com/original",
                "permalink": "https://aihot.example/items/a1",
                "source": "官方博客",
                "publishedAt": "2026-07-11T08:00:00Z",
                "category": "ai-models",
                "score": 82,
                "selected": True,
            }]
        })

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal["source"], "aihot")
        self.assertEqual(signal["source_label"], "AI HOT")
        self.assertEqual(signal["signal_type"], "trend")
        self.assertEqual(signal["content_kind"], "shift")
        self.assertEqual(signal["external_score"], 82)
        self.assertEqual(signal["url"], "https://aihot.example/items/a1")
        self.assertEqual(signal["original_url"], "https://example.com/original")
        self.assertEqual(signal["permalink"], "https://aihot.example/items/a1")

    def test_aihot_hot_topic_preserves_source_count_and_order(self):
        from collectors.aihot import parse_hot_topics

        signals = parse_hot_topics({"items": [{
            "id": "hot-1",
            "title": "Agent runtime security",
            "url": "https://example.com/source",
            "permalink": "https://aihot.example/items/hot-1",
            "sourceCount": 4,
            "signalCount": 9,
            "latestAt": "2026-07-11T08:00:00Z",
        }]})

        self.assertEqual(signals[0]["source_count"], 4)
        self.assertEqual(signals[0]["signal_count"], 9)
        self.assertEqual(signals[0]["source_rank"], 1)
        self.assertEqual(signals[0]["url"], "https://aihot.example/items/hot-1")

    def test_aihot_product_item_remains_context_not_demand(self):
        from collectors.aihot import parse_items

        signal = parse_items({"items": [{
            "id": "p1",
            "title": "新产品发布",
            "summary": "产品说明",
            "url": "https://example.com/product",
            "source": "产品官网",
            "category": "ai-products",
            "score": 71,
            "selected": True,
        }]})[0]

        self.assertEqual(signal["signal_type"], "trend")
        self.assertEqual(signal["content_kind"], "shift")

    def test_follow_builders_tweet_becomes_builder_signal(self):
        from collectors.follow_builders import parse_x_feed

        signals = parse_x_feed({
            "x": [{
                "name": "Builder",
                "handle": "builder",
                "bio": "AI product builder",
                "tweets": [{
                    "id": "1",
                    "text": "Built a new local-first agent workflow.",
                    "createdAt": "2026-07-11T08:00:00Z",
                    "url": "https://x.com/builder/status/1",
                    "likes": 20,
                    "retweets": 3,
                    "replies": 2,
                }],
            }]
        })

        self.assertEqual(len(signals), 1)
        signal = signals[0]
        self.assertEqual(signal["source"], "follow_builders")
        self.assertEqual(signal["source_label"], "Follow Builders")
        self.assertEqual(signal["content_kind"], "builder")
        self.assertEqual(signal["author"], "Builder")
        self.assertEqual(signal["popularity"], 25)
        self.assertEqual(signal["url"], "https://x.com/builder/status/1")

    def test_follow_builders_blog_requires_original_url(self):
        from collectors.follow_builders import parse_blog_feed

        signals = parse_blog_feed({"blogs": [
            {"name": "Official Blog", "title": "With link", "url": "https://example.com/post", "content": "Useful details"},
            {"name": "Official Blog", "title": "Without link", "url": "", "content": "Must be skipped"},
        ]})

        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["title"], "With link")
        self.assertEqual(signals[0]["content_kind"], "builder")

    def test_follow_builders_podcast_becomes_builder_signal_without_full_transcript(self):
        from collectors.follow_builders import parse_podcast_feed

        transcript = "A detailed builder conversation. " * 100
        signals = parse_podcast_feed({"podcasts": [{
            "name": "Builders Podcast",
            "title": "How the team validates demand",
            "guid": "ep-1",
            "url": "https://example.com/episode",
            "publishedAt": "2026-07-11T08:00:00Z",
            "transcript": transcript,
        }]})

        self.assertEqual(signals[0]["category"], "builder-podcast")
        self.assertEqual(signals[0]["content_kind"], "builder")
        self.assertLessEqual(len(signals[0]["text"]), 1600)


if __name__ == "__main__":
    unittest.main()
