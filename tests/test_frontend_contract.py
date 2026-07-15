import unittest
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class IdCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.tabs = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if values.get("data-view"):
            self.tabs.add(values["data-view"])


class FrontendContractTest(unittest.TestCase):
    def test_attention_first_page_structure_exists(self):
        parser = IdCollector()
        parser.feed((ROOT / "web" / "index.html").read_text(encoding="utf-8"))

        self.assertTrue({"dailyTitle", "attentionSummary", "streamTabs", "attentionBoard", "metricsDisclosure"}.issubset(parser.ids))
        self.assertEqual(parser.tabs, {"today", "need", "shift", "builder", "watch"})

    def test_frontend_renders_attention_and_stale_state(self):
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn("function renderAttention", script)
        self.assertIn("数据已过期", script)
        self.assertIn("本次更新部分降级", script)
        self.assertIn('data/status.json', script)
        self.assertIn("state.attention", script)

    def test_feedback_is_browser_local_and_exportable(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="feedbackExport"', html)
        self.assertIn('const FEEDBACK_KEY = "need-radar-feedback-v1"', script)
        self.assertIn("localStorage.setItem(FEEDBACK_KEY", script)
        self.assertIn("function exportFeedback", script)


if __name__ == "__main__":
    unittest.main()
