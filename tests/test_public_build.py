import unittest

from scripts.build_public import sanitize_payload, sanitize_status


class PublicBuildTest(unittest.TestCase):
    def test_public_payload_drops_personas_cache_paths_and_redacts_contact(self):
        payload = sanitize_payload({
            "generated_at": "2026-07-15T08:00:00+08:00",
            "meta": {
                "signals": 1,
                "semantic_gate_cache": {"path": "/Users/private/data/cache.json"},
                "persona_profiles": {"private": {"source_skill": "/Users/private/SKILL.md"}},
            },
            "needs": [{
                "id": "need-1",
                "title": "Contact me@example.com for a better export tool",
                "summary": "Repeated manual work",
                "sources": ["Example"],
                "evidence": [{"title": "Original", "url": "https://example.com/post?utm_source=test"}],
                "personas": {"private": "not public"},
            }],
            "watchlist": [],
            "attention": {"items": [], "limits": {}, "summary": {}},
        })

        serialized = str(payload)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("source_skill", serialized)
        self.assertNotIn("personas", serialized)
        self.assertIn("[redacted-email]", payload["needs"][0]["title"])
        self.assertEqual(payload["needs"][0]["evidence"][0]["url"], "https://example.com/post")

    def test_public_status_drops_stdout_and_errors(self):
        status = sanitize_status({
            "status": "degraded",
            "mode": "github",
            "collectors": [{"label": "x", "status": "failed", "err": "/Users/private/token", "tail": "secret"}],
        })

        self.assertNotIn("err", status["collectors"][0])
        self.assertNotIn("tail", status["collectors"][0])


if __name__ == "__main__":
    unittest.main()
