import unittest

from pydantic import ValidationError

from air.flows.code_review.result import ReviewComment, ReviewLine, ReviewResult


class ReviewResultTest(unittest.TestCase):
    def test_accepts_freeform_body(self) -> None:
        result = ReviewResult.model_validate(
            {"body": "## 结论\n\nLGTM", "should_notify": False}
        )

        self.assertEqual(result.body, "## 结论\n\nLGTM")
        self.assertEqual(result.comments, [])
        self.assertFalse(result.should_notify)

    def test_accepts_general_single_line_and_multiline_comments(self) -> None:
        result = ReviewResult(
            body="发现 3 个问题",
            comments=[
                ReviewComment(body="整体命名风格不统一"),
                ReviewComment(
                    body="新增行缺少校验",
                    old_path="app.py",
                    new_path="app.py",
                    start_line=ReviewLine(new_line=12),
                ),
                ReviewComment(
                    body="这段范围需要保持原子性",
                    old_path="old.py",
                    new_path="new.py",
                    start_line=ReviewLine(old_line=20, new_line=21),
                    end_line=ReviewLine(new_line=24),
                ),
            ],
        )

        self.assertFalse(result.comments[0].is_inline)
        self.assertTrue(result.comments[1].is_inline)
        self.assertFalse(result.comments[1].is_multiline)
        self.assertTrue(result.comments[2].is_multiline)

    def test_rejects_empty_or_non_positive_review_line(self) -> None:
        for values in ({}, {"old_line": 0}, {"new_line": -1}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                ReviewLine.model_validate(values)

    def test_rejects_incomplete_inline_position(self) -> None:
        invalid_comments = [
            {"body": "问题", "old_path": "app.py"},
            {"body": "问题", "old_path": "app.py", "new_path": "app.py"},
            {"body": "问题", "start_line": {"new_line": 1}},
            {"body": "问题", "end_line": {"new_line": 2}},
        ]
        for comment in invalid_comments:
            with self.subTest(comment=comment), self.assertRaises(ValidationError):
                ReviewComment.model_validate(comment)

    def test_defaults_to_notify_for_legacy_result(self) -> None:
        result = ReviewResult.model_validate({"body": "发现 1 个问题"})

        self.assertTrue(result.should_notify)

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
