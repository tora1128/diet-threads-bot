import unittest

from followup_existing import FOLLOWUP_MARKER, pending_followups


class FollowupExistingTests(unittest.TestCase):
    def test_skips_only_comments_that_already_received_the_followup(self):
        conversation = [
            {
                "id": "comment-1",
                "username": "reader1",
                "timestamp": "2026-10-03T01:00:00+00:00",
                "replied_to": {"id": "root-1"},
            },
            {
                "id": "old-reply",
                "text": "以前のご案内です",
                "username": "mayonaka_letter",
                "is_reply_owned_by_me": True,
                "replied_to": {"id": "comment-1"},
            },
            {
                "id": "comment-2",
                "username": "reader2",
                "timestamp": "2026-10-03T02:00:00+00:00",
                "replied_to": {"id": "root-1"},
            },
            {
                "id": "followup-reply",
                "text": FOLLOWUP_MARKER,
                "username": "mayonaka_letter",
                "is_reply_owned_by_me": True,
                "replied_to": {"id": "comment-2"},
            },
            {
                "id": "nested",
                "username": "reader3",
                "timestamp": "2026-10-03T03:00:00+00:00",
                "replied_to": {"id": "comment-1"},
            },
        ]

        result = pending_followups(
            "root-1",
            conversation,
            "mayonaka_letter",
        )
        self.assertEqual([entry["id"] for entry in result], ["comment-1"])


if __name__ == "__main__":
    unittest.main()
