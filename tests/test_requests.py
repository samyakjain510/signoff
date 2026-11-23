"""Unit tests for reading the person's own words out of Claude Code transcripts.

Run: python3 -m unittest discover -s tests
"""
import unittest

from signoff.requests import user_text


class UserText(unittest.TestCase):
    def test_plain_typed_message(self):
        rec = {"type": "user", "message": {"content": "Add a helpful button"}}
        self.assertEqual(user_text(rec), "Add a helpful button")

    def test_system_reminders_are_stripped(self):
        rec = {"type": "user", "message": {"content": "Ship it<system-reminder>internal note</system-reminder>"}}
        self.assertEqual(user_text(rec), "Ship it")

    def test_tool_results_are_not_typed_text(self):
        rec = {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}}
        self.assertIsNone(user_text(rec))

    def test_compaction_summary_is_claude_not_the_person(self):
        flagged = {"type": "user", "isCompactSummary": True, "message": {"content": "Summary of earlier work"}}
        unflagged = {"type": "user", "message": {"content":
                     "This session is being continued from a previous conversation that ran out of context."}}
        self.assertIsNone(user_text(flagged))
        self.assertIsNone(user_text(unflagged))

    def test_message_sent_mid_task_counts(self):
        rec = {"type": "attachment", "attachment": {
            "type": "queued_command", "prompt": "Split the site into two sections",
            "origin": {"kind": "human"}, "humanTurn": True}}
        self.assertEqual(user_text(rec), "Split the site into two sections")

    def test_mid_task_message_with_pasted_image(self):
        rec = {"type": "attachment", "attachment": {
            "type": "queued_command", "origin": {"kind": "human"},
            "prompt": [{"type": "text", "text": "Make this look like the screenshot"},
                       {"type": "image", "source": {"type": "base64", "data": "..."}}]}}
        self.assertEqual(user_text(rec), "Make this look like the screenshot")

    def test_queued_system_notice_does_not_count(self):
        rec = {"type": "attachment", "attachment": {
            "type": "queued_command", "prompt": "<task-notification>done</task-notification>",
            "origin": {"kind": "task-notification"}}}
        self.assertIsNone(user_text(rec))


if __name__ == "__main__":
    unittest.main()
