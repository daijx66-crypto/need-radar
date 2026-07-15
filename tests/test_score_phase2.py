import unittest
import datetime

from collectors._common import mk_signal
from scorer import score


def signal(**kwargs):
    base = {
        "id": "test-1",
        "source": "test",
        "source_label": "Reddit",
        "region": "海外",
        "lang": "en",
        "title": "",
        "text": "",
        "url": "https://example.com/post",
        "popularity": 18,
        "comments": 6,
        "signal_type": "question",
        "keywords": ["competitor", "monitoring", "reviews"],
    }
    base.update(kwargs)
    return score.featurize(mk_signal(**base))


class Phase2ScoringTest(unittest.TestCase):
    def test_github_mode_excludes_stale_local_browser_raw(self):
        files = [
            "/repo/data/raw/hackernews.json",
            "/repo/data/raw/opencli_twitter.json",
            "/repo/data/raw/bilibili.json",
        ]

        filtered = score.filter_raw_files(files, "github")

        self.assertEqual(filtered, ["/repo/data/raw/hackernews.json"])

    def test_old_signal_is_not_a_daily_need_candidate(self):
        old = signal(created_at="2017-05-11T16:57:02Z")
        current = datetime.datetime(2026, 7, 15, tzinfo=datetime.timezone.utc)

        self.assertFalse(score.is_recent_signal(old, as_of=current))

    def test_negative_recommendation_is_not_misread_as_tool_seeking(self):
        review = signal(
            source_label="App Store",
            title="Bad experience",
            text="I purchased an item and do not recommend this app. The seller ignored my refund request.",
            signal_type="complaint",
            keywords=["bad", "experience", "refund"],
        )

        gate = score.semantic_gate(review)

        self.assertFalse(gate["should_rank"])

    def test_conservative_cluster_does_not_merge_generic_image_overlap(self):
        first = signal(
            id="image-1",
            title="Looking for a tool to compress product images in bulk",
            text="We manually compress ecommerce images every day.",
            keywords=["tool", "product", "images", "compress"],
        )
        second = signal(
            id="image-2",
            source_label="Hacker News",
            title="Need an app to identify AI generated political images",
            text="Reviewers cannot identify political synthetic media.",
            keywords=["app", "political", "images", "identify"],
        )
        for item in (first, second):
            item["_gate"] = {"intent_type": "tool_seeking"}

        clusters = score.cluster([first, second])

        self.assertEqual(len(clusters), 2)

    def test_conservative_cluster_merges_strong_same_intent_topic(self):
        first = signal(
            id="reviews-1",
            title="Tool to monitor competitor app store reviews",
            keywords=["tool", "monitor", "competitor", "app", "reviews"],
        )
        second = signal(
            id="reviews-2",
            title="Need a tool that monitors competitor app reviews",
            keywords=["tool", "monitor", "competitor", "app", "reviews", "alerts"],
        )
        for item in (first, second):
            item["_gate"] = {"intent_type": "tool_seeking"}

        clusters = score.cluster([first, second])

        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]["members"]), 2)

    def test_webapps_how_to_existing_tool_is_noise(self):
        sig = signal(
            source_label="Stack Exchange · Web Applications",
            title="How can I pull a value from one column based on the values of another column?",
            text="I am using Google Sheets and need the formula for this row.",
            signal_type="question",
            keywords=["google", "sheets", "formula"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertFalse(gate["should_rank"])
        self.assertEqual(gate["noise_type"], "how_to_existing_tool")
        self.assertFalse(score.need_candidate(sig))

    def test_spreadsheet_formula_dollar_references_are_not_paid_cost(self):
        sig = signal(
            source_label="Stack Exchange · Web Applications",
            title='Ranking in google sheets error. =rank(H2,$H2:$H92)+Countifs($H2=$H2,$I2,"<="&$I2)',
            text="I need help fixing a Google Sheets formula.",
            signal_type="question",
            keywords=["google", "sheets", "rank", "formula"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "how_to_existing_tool")
        self.assertFalse(score.need_candidate(sig))

    def test_office_formatting_how_to_is_noise(self):
        sig = signal(
            source_label="Stack Exchange · Super User",
            title="How can I get rid of small capitals in the text in PowerPoint?",
            text="I can't remove the small capitals in a Title or add them to another in PowerPoint.",
            signal_type="question",
            keywords=["powerpoint", "text", "small", "capitals"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "how_to_existing_tool")
        self.assertFalse(score.need_candidate(sig))

    def test_link_drop_alternative_product_is_not_user_need(self):
        sig = signal(
            source_label="Hacker News",
            title="N8n.io – Workflow automation alternative to Zapier",
            text="",
            url="https://n8n.io/",
            signal_type="complaint",
            keywords=["n8n", "workflow", "automation", "alternative", "zapier"],
            popularity=728,
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "product_link_drop")
        self.assertFalse(score.need_candidate(sig))

    def test_v2ex_product_feedback_request_is_promotion_noise(self):
        sig = signal(
            source_label="V2EX",
            title="做了个 Launchpad 替代品（数不清第几个了），打磨了 9 个月，想听听大家的反馈",
            text="我们团队做了一个 macOS Launchpad 替代品，欢迎大家试用反馈。",
            signal_type="question",
            keywords=["launchpad", "替代品", "反馈"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "promotion")
        self.assertFalse(score.need_candidate(sig))

    def test_general_product_feedback_discussion_is_noise(self):
        sig = signal(
            source_label="V2EX",
            title="FaceTime 不同人使用反馈",
            text="之前推荐别人使用 FaceTime，朋友反馈非常卡。不知道其他人使用如何？",
            signal_type="complaint",
            keywords=["facetime", "反馈"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertFalse(score.need_candidate(sig))

    def test_profitable_saas_inspiration_is_market_research_noise(self):
        sig = signal(
            source_label="Hacker News",
            title="Ask HN: What is an example of a super simple SaaS that is profitable?",
            text="Looking to make 500$ a month - any examples of super simple SaaS that make at least 500 USD per month?",
            signal_type="question",
            keywords=["saas", "profitable", "examples"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "market_research")
        self.assertFalse(score.need_candidate(sig))

    def test_personal_vibe_coding_reflection_is_discussion_noise(self):
        sig = signal(
            source_label="V2EX",
            title="Vibe Coding 了两年，分享一下我对于 Vibe 的感想。",
            text="以下为个人观点，基本上全是暴论。我买不起订阅，所以借朋友账号体验。",
            signal_type="question",
            keywords=["vibe", "coding"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "discussion")
        self.assertFalse(score.need_candidate(sig))

    def test_consumer_phone_buying_advice_is_noise(self):
        sig = signal(
            source_label="V2EX",
            title="想换个大电池（9000mAh 以上）的手机，哪家的好？求推荐个型号",
            text="不玩手机游戏，主要就是日常 APP、视频之类的。",
            signal_type="question",
            keywords=["手机", "大电池", "求推荐"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "consumer_buy_advice")
        self.assertFalse(score.need_candidate(sig))

    def test_low_context_social_reply_tool_mention_is_noise(self):
        sig = signal(
            source="opencli_twitter",
            source_label="X/Twitter",
            title="@Le_choo_ga @ZoneXbez you need a tool to go through the files",
            text="query=need a tool lang:en",
            signal_type="question",
            popularity=0,
            keywords=["tool", "files"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "low_context_social_reply")
        self.assertFalse(score.need_candidate(sig))

    def test_creator_tool_roundup_is_noise(self):
        sig = signal(
            source="opencli_tiktok",
            source_label="TikTok",
            title="looking for apps for school is like back-to-school shopping but for free 😌 i rec a lot of apps",
            text="query=looking for app author=sleepytofuuuu shares=2455",
            signal_type="question",
            popularity=42270,
            keywords=["apps", "school", "recommend"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "creator_roundup")
        self.assertFalse(score.need_candidate(sig))

    def test_v2ex_self_product_launch_is_promotion_noise(self):
        sig = signal(
            source_label="V2EX",
            title="newtab01: 一个基于书签驱动、以列表显示的新标签页 Chrome 扩展",
            text="我知道站里已经有很多朋友发布过新标签页扩展了，不过我的这个新标签其实主要是为了满足自己的使用需求。",
            signal_type="question",
            keywords=["chrome", "扩展", "新标签页"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "promotion")
        self.assertFalse(score.need_candidate(sig))

    def test_stackoverflow_framework_bug_is_not_product_opportunity(self):
        sig = signal(
            source_label="Stack Exchange · Stack Overflow",
            title="How can I reset browser :user-invalid state when resetting an Angular Signal Form?",
            text="After resetting an Angular Signal Forms, the browser’s :user-invalid state remains on required inputs.",
            signal_type="question",
            keywords=["angular", "signal", "forms", "browser"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "developer_how_to")
        self.assertFalse(score.need_candidate(sig))

    def test_libreoffice_settings_how_to_is_noise(self):
        sig = signal(
            source_label="Stack Exchange · Super User",
            title="How to disable auto-complete in Libreoffice Writer?",
            text="I have noticed in LibreOffice Writer that it auto-completes words. Is there a way to permanently disable it?",
            signal_type="question",
            keywords=["libreoffice", "writer", "autocomplete"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "noise")
        self.assertEqual(gate["noise_type"], "how_to_existing_tool")
        self.assertFalse(score.need_candidate(sig))

    def test_tool_seeking_with_paid_workaround_is_real_need(self):
        sig = signal(
            source_label="Reddit",
            title="Looking for a tool to monitor competitor negative reviews across app stores",
            text=(
                "I run a small SaaS and pay a VA $200 per month to check App Store and "
                "Chrome Web Store reviews manually. Is there a tool that alerts me when "
                "competitors get repeated complaints?"
            ),
            signal_type="question",
            keywords=["competitor", "reviews", "alerts", "saas"],
        )

        gate = score.semantic_gate(sig)

        self.assertEqual(gate["label"], "real_need")
        self.assertTrue(gate["should_rank"])
        self.assertEqual(gate["source_tier"], "B")
        self.assertIn("付出代价", gate["purchase_reason"])
        self.assertTrue(score.need_candidate(sig))

    def test_need_contains_opportunity_card_fields(self):
        sig = signal(
            source_label="Reddit",
            title="Looking for a tool to monitor competitor negative reviews across app stores",
            text=(
                "I run a small SaaS and pay a VA $200 per month to check App Store and "
                "Chrome Web Store reviews manually. Is there a tool that alerts me when "
                "competitors get repeated complaints?"
            ),
            signal_type="question",
            keywords=["competitor", "reviews", "alerts", "saas"],
        )

        need = score.build_need({"seed": sig, "members": [sig]}, 1)

        self.assertEqual(need["source_tiers"], ["B"])
        self.assertEqual(need["opportunity"]["status"], "new")
        self.assertIn("purchase_reason", need["opportunity"])
        self.assertIn("current_workaround", need["opportunity"])
        self.assertIn("mvp", need["opportunity"])
        self.assertIn("validation", need["opportunity"])

    def test_need_emits_all_configured_personas(self):
        sig = signal(
            source_label="Reddit",
            title="Looking for a tool to monitor competitor negative reviews across app stores",
            text=(
                "I run a small SaaS and pay a VA $200 per month to check App Store and "
                "Chrome Web Store reviews manually. Is there a tool that alerts me when "
                "competitors get repeated complaints?"
            ),
            signal_type="question",
            keywords=["competitor", "reviews", "alerts", "saas"],
        )

        need = score.build_need({"seed": sig, "members": [sig]}, 1)

        expected = set(score.persona_keys())
        self.assertGreaterEqual(len(expected), 3)
        self.assertEqual(set(need["personas"]), expected)
        if "shulin" in need["personas"]:
            self.assertIn("真实尺寸", need["personas"]["shulin"])

    def test_persona_profiles_have_display_metadata(self):
        profiles = score.persona_profiles()

        if "shulin" in profiles:
            self.assertEqual(profiles["shulin"]["name"], "树林")
        for key in score.persona_keys():
            self.assertIn(key, profiles)
            self.assertTrue(profiles[key]["name"])
            self.assertTrue(profiles[key]["tag"])
            self.assertTrue(profiles[key]["avatar"])

    def test_semantic_gate_cache_records_deterministic_result(self):
        sig = signal(
            id="cache-1",
            source="opencli_tiktok",
            source_label="TikTok",
            title="Top 10 AI tools you should use in 2026",
            text="",
            signal_type="question",
            keywords=["ai", "tools"],
        )
        cache = {}

        first = score.semantic_gate_cached(sig, cache)
        second = score.semantic_gate_cached(sig, cache)

        self.assertEqual(first, second)
        self.assertEqual(len(cache), 1)
        rec = next(iter(cache.values()))
        self.assertEqual(rec["label"], first["label"])
        self.assertEqual(rec["gate"], first)
        self.assertIn("input_hash", rec)
        self.assertIn("updated_at", rec)

    def test_watchlist_keeps_social_candidates_outside_main_rank(self):
        sig = signal(
            id="watch-1",
            source="opencli_xiaohongshu",
            source_label="小红书",
            region="国内",
            lang="zh",
            title="Claude Code 太贵了，有没有便宜一点的自动化替代工具",
            text="现在每个月订阅成本有点高，想找一个能自动写脚本和改项目的小工具。",
            signal_type="complaint",
            popularity=23,
            keywords=["claude", "code", "太贵", "替代", "自动化"],
        )

        watchlist = score.build_watchlist([sig], used_keys=set(), limit=5)

        self.assertEqual(len(watchlist), 1)
        item = watchlist[0]
        self.assertEqual(item["source_label"], "小红书")
        self.assertIn(item["gate"], {"real_need", "possible_need"})
        self.assertEqual(item["source_tier"], "B")
        self.assertIn("reason", item)
        self.assertIn("候选", item["reason"])

    def test_watchlist_keeps_commercial_and_trend_context(self):
        producthunt = signal(
            id="ph-1",
            source="producthunt",
            source_label="Product Hunt",
            title="Lyto",
            text="One AI agent across your browser, tools, and messages.",
            url="https://www.producthunt.com/products/lyto",
            signal_type="launch",
            popularity=117,
            keywords=["ai", "agent", "browser"],
        )
        github = signal(
            id="gh-1",
            source="github_trending",
            source_label="GitHub Trending",
            title="browser-use/browser-use",
            text="Make websites accessible for AI agents · language=Python",
            url="https://github.com/browser-use/browser-use",
            signal_type="trend",
            popularity=88,
            keywords=["Python", "ai", "agents"],
        )

        watchlist = score.build_watchlist([producthunt, github], used_keys=set(), limit=5)

        self.assertEqual([item["source_label"] for item in watchlist], ["Product Hunt", "GitHub Trending"])
        self.assertEqual(watchlist[0]["source_tier"], "A")
        self.assertIn("商业", watchlist[0]["reason"])
        self.assertEqual(watchlist[1]["source_tier"], "C")
        self.assertIn("趋势", watchlist[1]["reason"])


if __name__ == "__main__":
    unittest.main()
