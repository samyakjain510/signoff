"""Unit tests for the tool: diff fitting, policy rules, quote checks, cleaning and the feed page.

Run: python3 -m unittest tests/test_tool.py
"""
import unittest

from signoff import checks, diffs, feed, llm, policy, review


def chunk(path: str, n: int) -> str:
    body = "".join(f"+line {i} of {path}\n" for i in range(n))
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -0,0 +1,{n} @@\n{body}"


class FitTests(unittest.TestCase):
    def test_tier0_files_are_never_dropped(self):
        big_ui = "".join(chunk(f"src/components/C{i}.tsx", 300) for i in range(20))
        diff = big_ui + chunk("supabase/migrations/007_drop_prefs.sql", 20) + chunk("package.json", 5)
        text, omitted, cut = diffs.fit(diff, total=20_000)
        self.assertIn("007_drop_prefs.sql", text)
        self.assertIn("package.json", text)
        self.assertTrue(cut)
        self.assertTrue(any("C19.tsx" in o for o in omitted))

    def test_lockfiles_and_binaries_are_skipped(self):
        diff = chunk("package-lock.json", 10) + chunk("public/logo.png", 1) + chunk("src/app.ts", 3)
        text, omitted, _ = diffs.fit(diff)
        self.assertNotIn("package-lock.json", text)
        self.assertIn("src/app.ts", text)
        self.assertEqual(len(omitted), 2)

    def test_tests_rank_below_pages(self):
        self.assertLess(diffs.tier("src/pages/index.astro"), diffs.tier("tests/home.spec.ts"))
        self.assertEqual(diffs.tier("db/migrations/1.sql"), 0)


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.pol = policy.load()

    def d(self, **kw):
        base = {"type": "user_facing", "who": "agent", "undo": "easy", "evidence_ok": True}
        base.update(kw)
        return base

    def test_default_tiers(self):
        self.assertEqual(policy.action(self.pol, self.d()), "notify")
        self.assertEqual(policy.action(self.pol, self.d(type="data_privacy")), "sign-off")
        self.assertEqual(policy.action(self.pol, self.d(type="removed_feature")), "sign-off")
        self.assertEqual(policy.action(self.pol, self.d(who="asked")), "silent")
        self.assertEqual(policy.action(self.pol, self.d(who="implied")), "notify")

    def test_hard_to_undo_raises(self):
        self.assertEqual(policy.action(self.pol, self.d(undo="hard")), "sign-off")
        self.assertEqual(policy.action(self.pol, self.d(who="implied", undo="hard")), "sign-off")
        self.assertEqual(policy.action(self.pol, self.d(who="asked", undo="hard")), "notify")

    def test_unproven_decision_is_never_held(self):
        self.assertEqual(policy.action(self.pol, self.d(type="data_privacy", evidence_ok=False)), "notify")

    def test_change_action_takes_the_strongest(self):
        decs = [self.d(who="asked"), self.d(), self.d(type="data_privacy")]
        self.assertEqual(policy.change_action(self.pol, decs), "sign-off")
        self.assertEqual(policy.change_action(self.pol, []), "silent")

    def test_custom_toml(self):
        pol = policy.tomllib.loads('[agent]\ndefault = "silent"\n[asked]\ndefault = "sign-off"\n')
        self.assertEqual(policy.action(pol, self.d()), "silent")
        self.assertEqual(policy.action(pol, self.d(who="asked")), "sign-off")


class QuoteCheckTests(unittest.TestCase):
    DIFF = "diff --git a/a.sql b/a.sql\n+++ b/a.sql\n+drop table email_prefs;\n"

    def out(self, who, rq, quote="drop table email_prefs;"):
        return {"summary": "", "spec_quote": "",
                "decisions": [{"type": "data_privacy", "what": "", "why_it_matters": "", "who": who, "undo": "hard",
                               "evidence": [{"file": "a.sql", "quote": "+" + quote}], "request_quote": rq}]}

    def test_asked_with_a_real_quote_stays_asked(self):
        o = review.check_output(self.out("asked", "drop the email prefs"), "Please drop the email   prefs table.", self.DIFF)
        self.assertEqual(o["decisions"][0]["who"], "asked")
        self.assertTrue(o["decisions"][0]["evidence_ok"])

    def test_asked_with_an_invented_quote_becomes_agent(self):
        o = review.check_output(self.out("asked", "delete all stored preferences"), "stop sending comment emails", self.DIFF)
        d = o["decisions"][0]
        self.assertEqual(d["who"], "agent")
        self.assertEqual(d["who_model"], "asked")
        self.assertIn("not found", d["who_note"])

    def test_invented_evidence_is_marked(self):
        o = review.check_output(self.out("agent", "", quote="truncate users;"), "", self.DIFF)
        self.assertFalse(o["decisions"][0]["evidence_ok"])


class PackageFromDiffTests(unittest.TestCase):
    def test_new_dependency_found_without_a_clone(self):
        diff = ('diff --git a/package.json b/package.json\n--- a/package.json\n+++ b/package.json\n@@ -5,6 +5,7 @@\n'
                '   "dependencies": {\n     "next": "16.0.0",\n+    "botid": "^1.4.0",\n     "react": "19.0.0"\n   },\n'
                '   "scripts": {\n+    "lint": "eslint ."\n')
        rec = {"sha": "pr1", "short": "pr1", "parents": [], "files": [{"status": "M", "path": "package.json"}]}
        found = [f for f in checks.run_checks(None, rec, diff) if f.check == "new_package"]
        self.assertEqual([f.text for f in found], ["dependencies: botid ^1.4.0"])


class SafetyTests(unittest.TestCase):
    def test_terminal_codes_are_removed(self):
        self.assertEqual(llm.safe("ok\x1b[31mred\x1b[0m\x1b]0;title\x07 done\x00"), "okred done")

    def test_feed_page_cannot_be_injected(self):
        ch = {"id": "c1", "kind": "commit", "title": "</script><script>alert(1)</script>", "date": "2026-11-01", "url": "",
              "agent": "claude", "spec_source": "", "spec_carried": False, "findings": []}
        rev = {"c1": {"out": {"summary": "<img src=x onerror=alert(1)>", "spec_quote": "", "spec_quote_ok": False,
                              "decisions": []}}}
        page = feed.html_feed(feed.feed_data("demo", [ch], rev, policy.load()))
        self.assertNotIn("</script><script>", page)
        self.assertNotIn("<img src=x", page)
        self.assertEqual(page.count("<script>"), 1)


if __name__ == "__main__":
    unittest.main()
