import datetime as dt
import unittest

from auto_reply import is_free_reading_post
from free_reading import generate_free_reading_post


class FreeReadingPostTests(unittest.TestCase):
    def test_uses_posting_date_and_comment_only_call_to_action(self):
        post = generate_free_reading_post(dt.date(2026, 10, 4))

        self.assertIn("本日限定10/4", post)
        self.assertIn("先着10名", post)
        self.assertIn("コメント", post)
        self.assertIn("鑑定希望", post)
        self.assertNotIn("DM", post)
        self.assertTrue(is_free_reading_post(post))
        self.assertLessEqual(len(post), 500)


if __name__ == "__main__":
    unittest.main()
