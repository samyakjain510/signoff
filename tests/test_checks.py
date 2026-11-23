"""Unit tests for the diff parsers and exact code checks.

Run: python3 -m unittest discover -s tests
"""
import unittest

from signoff import checks, gitlog
from signoff.label import trim_diff, verify_quotes

DIFF = """diff --git a/src/pages/about.astro b/src/pages/about.astro
--- a/src/pages/about.astro
+++ b/src/pages/about.astro
@@ -10,3 +10,5 @@
 <p>Hello</p>
-<a href="https://linkedin.com/in/x">LinkedIn</a>
+<a href="https://linkedin.com/in/y">LinkedIn</a>
+<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">
+<svg viewBox="0 0 10 10" role="img" aria-label="chart"></svg>
diff --git a/supabase/migrations/002.sql b/supabase/migrations/002.sql
--- /dev/null
+++ b/supabase/migrations/002.sql
@@ -0,0 +1,2 @@
+alter table public.profiles enable row level security;
+create policy "own" on public.profiles for select using (auth.uid() = id);
diff --git a/lib/email.ts b/lib/email.ts
--- a/lib/email.ts
+++ b/lib/email.ts
@@ -1,1 +1,3 @@
+import nodemailer from "nodemailer";
+const key = process.env.GMAIL_APP_PASSWORD;
 export {};
"""

REC = {
    "sha": "abc1234def", "short": "abc1234", "parents": [], "files": [
        {"status": "M", "path": "src/pages/about.astro", "additions": 3, "deletions": 1},
        {"status": "A", "path": "supabase/migrations/002.sql", "additions": 2, "deletions": 0},
        {"status": "M", "path": "lib/email.ts", "additions": 2, "deletions": 0},
        {"status": "D", "path": "app/unsubscribe/page.tsx", "additions": 0, "deletions": 40},
    ],
}


def findings_by_check():
    checks._DIFF_CACHE[REC["sha"]] = checks.parse_diff(DIFF)
    out = {}
    for f in checks.file_checks(REC) + checks.line_checks(REC):
        out.setdefault(f.check, []).append(f)
    return out


class ParseDiff(unittest.TestCase):
    def test_line_numbers_follow_hunk_header(self):
        parsed = checks.parse_diff(DIFF)
        added = parsed["src/pages/about.astro"]["added"]
        self.assertEqual(added[0][0], 11)  # first added line comes after one context line at 10
        removed = parsed["src/pages/about.astro"]["removed"]
        self.assertEqual(removed[0][0], 11)

    def test_new_file_is_parsed(self):
        parsed = checks.parse_diff(DIFF)
        self.assertEqual(len(parsed["supabase/migrations/002.sql"]["added"]), 2)


class Checks(unittest.TestCase):
    def setUp(self):
        self.f = findings_by_check()

    def test_aria_role_is_not_an_access_rule(self):
        texts = [f.text for f in self.f.get("access_rules", [])]
        self.assertFalse(any('role="img"' in t for t in texts))

    def test_sql_policies_are_access_rules(self):
        self.assertEqual(len(self.f["access_rules"]), 2)

    def test_plain_links_are_not_outside_services(self):
        hosts = [f.text for f in self.f.get("outside_service", [])]
        self.assertNotIn("linkedin.com", hosts)

    def test_loaded_stylesheet_is_an_outside_service(self):
        hosts = [f.text for f in self.f.get("outside_service", [])]
        self.assertEqual(hosts, ["fonts.googleapis.com"])

    def test_messaging_setting_migration_and_removed_page(self):
        self.assertIn("messages_users", self.f)
        self.assertEqual([f.text for f in self.f["new_setting_or_secret"]], ["GMAIL_APP_PASSWORD"])
        self.assertIn("data_shape_change", self.f)
        self.assertEqual(self.f["page_removed"][0].file, "app/unsubscribe/page.tsx")


class GitlogParsers(unittest.TestCase):
    def test_numstat_handles_renames_and_binaries(self):
        raw = "3\t1\tsrc/a.ts\0-\t-\tpublic/logo.png\0" + "5\t0\t\0old/b.ts\0new/b.ts\0"
        out = gitlog.parse_numstat_z(raw)
        self.assertEqual(out["src/a.ts"], (3, 1))
        self.assertEqual(out["public/logo.png"], (None, None))
        self.assertEqual(out["new/b.ts"], (5, 0))

    def test_name_status_handles_renames(self):
        raw = "M\0src/a.ts\0R100\0old/b.ts\0new/b.ts\0D\0gone.ts\0"
        out = gitlog.parse_name_status_z(raw)
        self.assertEqual([f["status"] for f in out], ["M", "R", "D"])
        self.assertEqual(out[1]["old_path"], "old/b.ts")

    def test_agent_detection(self):
        self.assertEqual(gitlog.agent_of(["Claude Opus 4.7 <noreply@anthropic.com>"]), "claude")
        self.assertIsNone(gitlog.agent_of(["Jane Doe <jane@example.com>"]))


class Labeling(unittest.TestCase):
    def test_trim_drops_lockfiles(self):
        diff = DIFF + "diff --git a/package-lock.json b/package-lock.json\n+++ b/package-lock.json\n+{}\n"
        text, omitted, _ = trim_diff(diff)
        self.assertNotIn("package-lock.json\n+{}", text)
        self.assertTrue(any("package-lock.json" in o for o in omitted))

    def test_quotes_must_exist_in_diff(self):
        label = {"decisions": [{"evidence": [
            {"file": "lib/email.ts", "quote": '+import nodemailer from "nodemailer";'},
            {"file": "lib/email.ts", "quote": "sendEmail(user)"},
        ]}]}
        ok, total, bad = verify_quotes(label, DIFF)
        self.assertEqual((ok, total), (1, 2))
        self.assertEqual(bad, ["sendEmail(user)"])


if __name__ == "__main__":
    unittest.main()
