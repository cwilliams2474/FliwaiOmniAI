import unittest

from app.codex_utils import parse_codex_json, safe_relative_path, unified_content_diff


class CodexSafetyTests(unittest.TestCase):
    def test_safe_relative_path(self):
        self.assertEqual(safe_relative_path('src/app/main.py'), 'src/app/main.py')

    def test_parent_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            safe_relative_path('../secrets.txt')

    def test_absolute_path_is_rejected(self):
        with self.assertRaises(ValueError):
            safe_relative_path('/etc/passwd')

    def test_structured_response_parses(self):
        result = parse_codex_json('{"summary":"ok","answer":"done","files":[],"test_plan":[],"risks":[]}')
        self.assertEqual(result['summary'], 'ok')
        self.assertEqual(result['files'], [])

    def test_unified_diff_reports_old_and_new_content(self):
        diff = unified_content_diff('src/a.py', 'x = 1\n', 'x = 2\n')
        self.assertIn('--- a/src/a.py', diff)
        self.assertIn('+++ b/src/a.py', diff)
        self.assertIn('-x = 1', diff)
        self.assertIn('+x = 2', diff)

    def test_unstructured_response_is_safe(self):
        result = parse_codex_json('plain response')
        self.assertEqual(result['files'], [])
        self.assertIn('plain response', result['answer'])


if __name__ == '__main__':
    unittest.main()
