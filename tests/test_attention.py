import copy
import datetime
import gc
import importlib
import json
import tempfile
import unittest
import warnings
from pathlib import Path


AS_OF = datetime.datetime(2026, 7, 11, 8, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=8)))


def need(title="Agent 工作流太碎", url="https://example.com/need", score=68, evidence_count=1):
    return {
        "id": "need-001",
        "title": title,
        "summary": "用户反复手工切换工具。",
        "region": "国内",
        "sources": ["V2EX"],
        "source_tier_labels": ["B 抱怨求助"],
        "signal_count": evidence_count,
        "evidence": [{
            "url": url,
            "source_label": "V2EX",
            "title": title,
            "created_at": "2026-07-11T06:30:00+08:00",
        }] if url else [],
        "demand_score": {"total": score, "dims": {}},
        "opportunity": {"purchase_reason": "用户已付出重复时间成本。"},
        "verdict_label": "值得一试",
    }


def signal(kind="shift", title="新模型发布", url="https://example.com/shift", score=76, source="aihot"):
    return {
        "id": f"{source}-{title}",
        "source": source,
        "source_label": "AI HOT" if source == "aihot" else "Follow Builders",
        "title": title,
        "text": "新的 Agent 能力已经发布。",
        "url": url,
        "created_at": "2026-07-11T07:30:00Z",
        "popularity": score,
        "external_score": score,
        "content_kind": kind,
        "category": "ai-models" if kind == "shift" else "builder-x",
        "_gate": {"source_tier": "C"},
    }


PROFILE = {
    "attention": {
        "focus_keywords": ["Agent", "自动化"],
        "deprioritize_keywords": ["娱乐"],
        "preferred_sources": ["AI HOT", "Follow Builders", "V2EX"],
        "now_limit": 2,
        "later_limit": 1,
    }
}


class AttentionTest(unittest.TestCase):
    def test_score_module_closes_static_json_files(self):
        import scorer.score as score

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            importlib.reload(score)
            gc.collect()

        resource_warnings = [row for row in caught if issubclass(row.category, ResourceWarning)]
        self.assertEqual(resource_warnings, [])

    def test_stable_id_uses_canonical_url_not_mutable_title(self):
        from scorer.attention import stable_id

        first = stable_id("need", "https://example.com/item", "旧标题", "V2EX")
        second = stable_id("need", "https://example.com/item", "新标题", "V2EX")

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("need-"))

    def test_first_snapshot_labels_items_without_fake_new_or_rank_delta(self):
        from scorer.attention import build_attention

        result = build_attention([need()], [signal()], PROFILE, previous=None, as_of=AS_OF)

        self.assertEqual(result["summary"]["now"], 2)
        self.assertTrue(all(item["change_label"] == "首份快照" for item in result["items"]))
        self.assertTrue(all(item["is_new"] is False for item in result["items"]))
        self.assertTrue(all(item["rank_delta"] is None for item in result["items"]))

    def test_cross_day_diff_tracks_new_rank_score_streak_and_evidence(self):
        from scorer.attention import build_attention, stable_id

        existing_id = stable_id("need", "https://example.com/need", "Agent 工作流太碎", "V2EX")
        previous = {
            "date": "2026-07-10",
            "items": [{
                "stable_id": existing_id,
                "rank": 2,
                "source_score": 64,
                "evidence_count": 1,
                "streak_days": 2,
            }],
        }
        result = build_attention(
            [need(score=70, evidence_count=3)],
            [signal(title="今天第一次出现的模型", url="https://example.com/new", score=65)],
            PROFILE,
            previous=previous,
            as_of=AS_OF,
        )
        rows = {item["stable_id"]: item for item in result["items"]}
        existing = rows[existing_id]
        new_row = rows[stable_id("shift", "https://example.com/new", "今天第一次出现的模型", "AI HOT")]

        self.assertEqual(existing["streak_days"], 3)
        self.assertEqual(existing["score_delta"], 6)
        self.assertEqual(existing["evidence_delta"], 2)
        self.assertEqual(existing["rank_delta"], 1)
        self.assertTrue(new_row["is_new"])
        self.assertEqual(new_row["change_label"], "今日新增")

    def test_attention_budget_and_missing_link_demotion(self):
        from scorer.attention import build_attention

        signals = [
            signal(title="高优先级变化", url="https://example.com/high", score=90),
            signal(kind="builder", title="建造者实践", url="https://example.com/builder", score=70, source="follow_builders"),
            signal(title="稍后看的变化", url="https://example.com/low", score=60),
            signal(title="没有证据链接", url="", score=99),
        ]
        result = build_attention([need(score=80)], signals, PROFILE, previous=None, as_of=AS_OF)

        priorities = [item["priority"] for item in result["items"]]
        self.assertEqual(priorities.count("now"), 2)
        self.assertEqual(priorities.count("later"), 1)
        missing = next(item for item in result["items"] if item["title"] == "没有证据链接")
        self.assertEqual(missing["priority"], "ignore")
        self.assertIn("缺少原始链接", missing["why_ignore"])

    def test_old_signal_cannot_be_labeled_as_today(self):
        from scorer.attention import build_attention

        old = signal(title="一周前的热点", score=90)
        old["created_at"] = "2026-07-01T08:00:00Z"
        result = build_attention([], [old], PROFILE, previous=None, as_of=AS_OF)
        row = result["items"][0]

        self.assertTrue(row["is_stale"])
        self.assertEqual(row["priority"], "ignore")
        self.assertIn("新鲜度窗口", row["why_ignore"])

    def test_no_kind_quota_forces_low_quality_item_into_now(self):
        from scorer.attention import build_attention

        weak_builder = signal(kind="builder", title="短促销动态", score=45, source="follow_builders")
        result = build_attention(
            [need(title="明确的高分需求", score=75)],
            [weak_builder],
            PROFILE,
            previous=None,
            as_of=AS_OF,
        )
        now_rows = [row for row in result["items"] if row["priority"] == "now"]

        self.assertEqual([row["kind"] for row in now_rows], ["need"])

    def test_kind_caps_prevent_one_feed_from_monopolizing_attention(self):
        from scorer.attention import build_attention

        profile = copy.deepcopy(PROFILE)
        profile["attention"]["now_limit"] = 5
        signals = [
            signal(title=f"重要变化 {index}", url=f"https://example.com/shift-{index}", score=95 - index)
            for index in range(6)
        ]
        result = build_attention(
            [need(title="达到阈值的新需求", score=70)],
            signals,
            profile,
            previous=None,
            as_of=AS_OF,
        )
        now_rows = [row for row in result["items"] if row["priority"] == "now"]

        self.assertLessEqual(sum(row["kind"] == "shift" for row in now_rows), 3)
        self.assertIn("need", {row["kind"] for row in now_rows})

    def test_uncurated_trend_popularity_cannot_take_all_now_slots(self):
        from scorer.attention import build_attention

        uncurated = {
            "id": "hf-hot",
            "source": "huggingface",
            "source_label": "Hugging Face",
            "title": "一个热度很高但未经精选的模型",
            "text": "模型条目",
            "url": "https://huggingface.co/example/model",
            "created_at": "2026-07-11T07:00:00Z",
            "popularity": 10000,
            "signal_type": "trend",
            "_gate": {"source_tier": "C"},
        }
        result = build_attention(
            [need(title="明确的 Agent 需求", score=68)],
            [signal(title="AI HOT 精选变化", score=75), uncurated],
            PROFILE,
            previous=None,
            as_of=AS_OF,
        )
        now_rows = [row for row in result["items"] if row["priority"] == "now"]

        self.assertEqual({row["kind"] for row in now_rows}, {"need", "shift"})
        self.assertNotIn("一个热度很高但未经精选的模型", {row["title"] for row in now_rows})

    def test_personalization_does_not_mutate_original_demand_score(self):
        from scorer.attention import build_attention

        original = need(title="Agent 自动化需求", score=61)
        before = copy.deepcopy(original)

        result = build_attention([original], [], PROFILE, previous=None, as_of=AS_OF)

        self.assertEqual(original, before)
        self.assertEqual(result["items"][0]["source_score"], 61)
        self.assertGreater(result["items"][0]["attention_score"], 61)

    def test_snapshot_round_trip_uses_latest_earlier_date(self):
        from scorer.attention import load_previous_snapshot, save_snapshot

        with tempfile.TemporaryDirectory() as tmp:
            attention = {"generated_at": AS_OF.isoformat(), "items": [{"stable_id": "need-a", "rank": 1}]}
            history = save_snapshot(attention, tmp, as_of=AS_OF)
            saved = json.loads((Path(tmp) / "2026-07-11.json").read_text(encoding="utf-8"))

            self.assertFalse(history["has_previous"])
            self.assertEqual(saved["date"], "2026-07-11")
            self.assertIsNone(load_previous_snapshot(tmp, as_of=AS_OF))

            older = {"date": "2026-07-10", "items": [{"stable_id": "need-a", "rank": 2}]}
            (Path(tmp) / "2026-07-10.json").write_text(json.dumps(older), encoding="utf-8")
            loaded = load_previous_snapshot(tmp, as_of=AS_OF)
            self.assertEqual(loaded["date"], "2026-07-10")

    def test_score_payload_gets_attention_history_and_stable_ids(self):
        from scorer.score import attach_attention

        payload = {
            "generated_at": AS_OF.isoformat(),
            "meta": {},
            "needs": [need()],
            "watchlist": [{
                "id": "watch-001",
                "title": "观察中的工具变化",
                "source_label": "GitHub Trending",
                "url": "https://example.com/watch",
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = attach_attention(payload, [signal()], PROFILE, tmp, as_of=AS_OF)

            self.assertIn("attention", result)
            self.assertIn("history", result)
            self.assertEqual(result["history"]["current_date"], "2026-07-11")
            self.assertTrue(result["needs"][0]["stable_id"].startswith("need-"))
            self.assertTrue(result["watchlist"][0]["stable_id"].startswith("watch-"))
            self.assertGreaterEqual(result["attention"]["summary"]["now"], 1)


if __name__ == "__main__":
    unittest.main()
