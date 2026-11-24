import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from avt.audit import audit_html  # noqa: E402
from avt.fanout import expand  # noqa: E402
from avt.logs import analyze  # noqa: E402
from avt.robots import Robots  # noqa: E402
from avt.score import cites_domain, score, wilson  # noqa: E402


def data(name):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as fh:
        return fh.read()


class RobotsTests(unittest.TestCase):
    def test_longest_match_and_allow_tie(self):
        r = Robots("User-agent: *\nDisallow: /docs/\nAllow: /docs/public/\n")
        self.assertFalse(r.allowed("anybot", "/docs/secret"))
        self.assertTrue(r.allowed("anybot", "/docs/public/page"))

    def test_specific_group_beats_wildcard(self):
        r = Robots("User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /\n")
        self.assertTrue(r.allowed("GPTBot", "/x"))
        self.assertFalse(r.allowed("ClaudeBot", "/x"))

    def test_wildcard_and_anchor(self):
        r = Robots("User-agent: *\nDisallow: /*.pdf$\n")
        self.assertFalse(r.allowed("b", "/a/b.pdf"))
        self.assertTrue(r.allowed("b", "/a/b.pdf?x=1"))

    def test_empty_disallow_allows(self):
        self.assertTrue(Robots("User-agent: *\nDisallow:\n").allowed("b", "/x"))


class AuditTests(unittest.TestCase):
    def test_good_page_scores_high(self):
        rep = audit_html(data("page.good.html"), "https://www.example.com/aeo",
                         Robots(data("robots.example.txt")), llms_status=404)
        by = {c.id: c for c in rep.checks}
        self.assertEqual(by["robots_retrieval"].earned, 1.0)
        self.assertEqual(by["answer_first"].earned, 1.0)
        self.assertEqual(by["freshness"].earned, 1.0)
        self.assertIn("GPTBot", rep.training_blocked)
        self.assertGreaterEqual(rep.score, 90)

    def test_blocked_retrieval_bot_loses_points(self):
        rep = audit_html(data("page.good.html"), "https://www.example.com/private/x",
                         Robots(data("robots.example.txt")))
        by = {c.id: c for c in rep.checks}
        self.assertLess(by["robots_retrieval"].earned, 1.0)

    def test_empty_shell_fails(self):
        rep = audit_html("<html><body><div id=root></div></body></html>", "http://x.test/")
        self.assertLess(rep.score, 20)


class LogTests(unittest.TestCase):
    def test_sample_log(self):
        with open(os.path.join(ROOT, "data", "sample_access.log"), encoding="utf-8") as fh:
            stats = analyze(fh)
        meta = stats.pop("_meta")
        self.assertEqual(meta["requests"], 420)
        self.assertIn("GPTBot", stats)
        self.assertNotIn("Googlebot", stats)
        self.assertEqual(stats["GPTBot"]["purpose"], "training")


class ScoreTests(unittest.TestCase):
    def test_wilson_bounds(self):
        lo, hi = wilson(5, 10)
        self.assertAlmostEqual(lo, 0.237, places=2)
        self.assertAlmostEqual(hi, 0.763, places=2)
        self.assertEqual(wilson(0, 0), (0.0, 0.0))

    def test_domain_match(self):
        self.assertTrue(cites_domain(["https://www.a.com/x"], "a.com"))
        self.assertTrue(cites_domain([{"url": "https://blog.a.com/x"}], "a.com"))
        self.assertFalse(cites_domain(["https://nota.com/x"], "a.com"))

    def test_position_and_sov(self):
        recs = [
            {"prompt_id": "p", "engine": "e", "ts": "2026-10-05",
             "answer": "Rival is fine, Acme is better.", "citations": []},
            {"prompt_id": "p", "engine": "e", "ts": "2026-10-05",
             "answer": "Acme wins.", "citations": ["https://acme.com/a"]},
        ]
        res = score(recs, "Acme", [], "acme.com", {"Rival": ["Rival"]})["e"]
        self.assertEqual(res["runs"], 2)
        self.assertEqual(res["mention_rate"], 1.0)
        self.assertEqual(res["avg_position"], 1.5)
        self.assertEqual(res["citation_rate"], 0.5)
        self.assertAlmostEqual(res["share_of_voice"], 2 / 3)

    def test_sample_file_runs(self):
        with open(os.path.join(ROOT, "data", "responses.sample.jsonl"), encoding="utf-8") as fh:
            recs = [json.loads(x) for x in fh]
        res = score(recs, "Lumen Notes", [], "lumennotes.example",
                    {"Quillpad": ["Quillpad"], "Notebase": ["Notebase"]}, "week")
        self.assertEqual(len(res), 4)


class FanoutTests(unittest.TestCase):
    def test_expansion_counts_and_dedup(self):
        cfg = json.loads(data("fanout.example.json"))
        rows = list(expand(cfg, "Acme"))
        # 2 persona templates x3 + 2 competitor templates (1 x2, 1 x2x3) + 2 plain + 2 brand
        self.assertEqual(len(rows), 6 + 2 + 6 + 2 + 2)
        self.assertEqual(len({r["id"] for r in rows}), len(rows))


if __name__ == "__main__":
    unittest.main()
