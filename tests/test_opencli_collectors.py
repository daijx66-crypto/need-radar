import unittest

from collectors import _opencli
from collectors.opencli_xiaohongshu import keep_row as keep_xhs_row, row_to_signal as xhs_row_to_signal
from collectors.opencli_tiktok import keep_row as keep_tiktok_row, row_to_signal as tiktok_row_to_signal
from collectors.opencli_twitter import keep_row as keep_twitter_row, row_to_signal as twitter_row_to_signal


class OpenCliCollectorTest(unittest.TestCase):
    def test_parse_human_count_handles_chinese_and_english_units(self):
        self.assertEqual(_opencli.parse_human_count("7.8万"), 78000)
        self.assertEqual(_opencli.parse_human_count("1.2k"), 1200)
        self.assertEqual(_opencli.parse_human_count("3,456"), 3456)
        self.assertEqual(_opencli.parse_human_count(None), 0)

    def test_xiaohongshu_row_becomes_standard_signal(self):
        sig = xhs_row_to_signal(
            {
                "rank": 1,
                "title": "有没有好用的 AI 简历工具？",
                "author": "测试作者",
                "likes": "1.2万",
                "url": "https://www.xiaohongshu.com/search_result/abc",
                "published_at": "2026-06-28",
            },
            query="AI 简历工具",
        )

        self.assertEqual(sig["source"], "opencli_xiaohongshu")
        self.assertEqual(sig["source_label"], "小红书")
        self.assertEqual(sig["popularity"], 12000)
        self.assertEqual(sig["signal_type"], "question")
        self.assertIn("AI", sig["text"])

    def test_social_tool_roundups_are_not_kept_as_need_signals(self):
        self.assertFalse(keep_tiktok_row({"desc": "Top 10 AI tools you should use in 2026"}))
        self.assertFalse(keep_tiktok_row({"desc": "I Can't Find Google available"}))
        self.assertFalse(keep_tiktok_row({"desc": "Pokémon Legends ZA is an Overpriced Disappointment"}))
        self.assertFalse(keep_tiktok_row({"desc": "felt like I was in pakistan (super overpriced tho yikes) #appna"}))
        self.assertFalse(keep_twitter_row({"text": "https://t.co/abcdef"}))
        self.assertFalse(keep_xhs_row({"title": "AI做PPT零基础终极教程！"}))
        self.assertFalse(keep_xhs_row({"title": "2026 AI Agent到底哪款更好用？", "author": "AI实战派Pro"}))
        self.assertFalse(keep_xhs_row({"title": "整理了好用的AI工具（附清单"}))
        self.assertFalse(keep_xhs_row({"title": "Cursor太贵？分享三个免费AI编程方案"}))
        self.assertTrue(keep_xhs_row({"title": "有没有好用的 AI 简历工具？"}))

    def test_tiktok_row_becomes_standard_signal(self):
        sig = tiktok_row_to_signal(
            {
                "rank": 2,
                "desc": "Looking for a better AI tool to summarize meetings",
                "author": "maker",
                "plays": 770700,
                "likes": 54400,
                "comments": 1619,
                "shares": 10800,
                "url": "https://www.tiktok.com/@maker/video/123",
            },
            query="AI tool",
        )

        self.assertEqual(sig["source"], "opencli_tiktok")
        self.assertEqual(sig["region"], "海外")
        self.assertEqual(sig["popularity"], 94895)
        self.assertEqual(sig["comments"], 1619)
        self.assertEqual(sig["signal_type"], "question")

    def test_twitter_row_becomes_standard_signal(self):
        sig = twitter_row_to_signal(
            {
                "id": "123",
                "author": "founder",
                "text": "Need a tool that monitors AI app reviews",
                "likes": 12,
                "retweets": 3,
                "replies": 4,
                "views": "1,200",
                "created_at": "Sun Jun 28 07:42:19 +0000 2026",
                "url": "https://x.com/i/status/123",
            },
            query="need a tool",
        )

        self.assertEqual(sig["source"], "opencli_twitter")
        self.assertEqual(sig["source_label"], "X/Twitter")
        self.assertEqual(sig["popularity"], 29)
        self.assertEqual(sig["signal_type"], "question")


if __name__ == "__main__":
    unittest.main()
