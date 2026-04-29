import unittest

from pydantic import ValidationError

from air.flows.code_review.result import ReviewResult


class ReviewResultTest(unittest.TestCase):
    def test_accepts_freeform_body(self) -> None:
        result = ReviewResult.model_validate({"body": "## 结论\n\nLGTM"})

        self.assertEqual(result.body, "## 结论\n\nLGTM")

    def test_rejects_legacy_summary_and_issues(self) -> None:
        with self.assertRaises(ValidationError):
            ReviewResult.model_validate(
                {
                    "summary": "发现 1 个需要处理的问题。",
                    "issues": [],
                }
            )


if __name__ == "__main__":
    unittest.main()
