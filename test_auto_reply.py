import datetime as dt
import unittest

from auto_reply import (
    FREE_READING_REPLIES,
    is_free_reading_post,
    select_reply_text,
    should_skip_reply,
    unanswered_direct_replies,
)


class AutoReplyTests(unittest.TestCase):
    def test_skips_questions_and_sensitive_content(self):
        self.assertEqual(should_skip_reply("どうすれば復縁できますか？"), "質問")
        self.assertEqual(should_skip_reply("薬について教えて"), "要手動確認の内容")
        self.assertIsNone(should_skip_reply("今日も心に響きました"))

    def test_reply_choice_is_deterministic(self):
        first = select_reply_text("reply-123", "ありがとうございます")
        second = select_reply_text("reply-123", "ありがとうございます")
        self.assertEqual(first, second)

    def test_free_reading_posts_use_profile_site_reply(self):
        root_text = "【無料鑑定】コメントに『鑑定希望』と書いてください"
        self.assertTrue(is_free_reading_post(root_text))
        selected = select_reply_text("reply-456", "鑑定希望です", root_text)
        self.assertIn(selected, FREE_READING_REPLIES)
        self.assertIn("プロフィール", selected)
        self.assertIn("フォロー", selected)
        self.assertIn("鑑定書", selected)
        self.assertNotIn("LINE", selected)
        self.assertGreater(len(selected), 70)

        replies = {
            select_reply_text(f"reply-{index}", "鑑定希望です", root_text)
            for index in range(20)
        }
        self.assertGreater(len(replies), 1)

    def test_regular_posts_keep_general_replies(self):
        root_text = "今日の恋愛運をお届けします"
        self.assertFalse(is_free_reading_post(root_text))
        self.assertNotEqual(
            select_reply_text("reply-789", "読みました", root_text),
            select_reply_text("reply-789", "読みました", "無料鑑定を受付中"),
        )

    def test_excludes_owned_answered_and_nested_replies(self):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        conversation = [
            {
                "id": "external-1",
                "text": "届きました🌙",
                "timestamp": now,
                "username": "reader1",
                "is_reply_owned_by_me": False,
                "replied_to": {"id": "root-1"},
            },
            {
                "id": "mine-1",
                "text": "ありがとう",
                "timestamp": now,
                "username": "mayonaka_letter",
                "is_reply_owned_by_me": True,
                "replied_to": {"id": "external-1"},
            },
            {
                "id": "external-2",
                "text": "素敵です",
                "timestamp": now,
                "username": "reader2",
                "is_reply_owned_by_me": False,
                "replied_to": {"id": "root-1"},
            },
            {
                "id": "nested-1",
                "text": "横から失礼します",
                "timestamp": now,
                "username": "reader3",
                "is_reply_owned_by_me": False,
                "replied_to": {"id": "external-2"},
            },
        ]

        result = unanswered_direct_replies(
            "root-1", conversation, "mayonaka_letter", 48
        )
        self.assertEqual([item["id"] for item in result], ["external-2"])


if __name__ == "__main__":
    unittest.main()
