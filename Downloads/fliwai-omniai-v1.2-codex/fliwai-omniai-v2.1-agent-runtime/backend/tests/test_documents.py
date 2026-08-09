import unittest

from app.documents import chunk_text, score_chunk


class DocumentRetrievalTests(unittest.TestCase):
    def test_chunk_text_preserves_content_and_splits_long_text(self):
        text = 'alpha ' * 600
        chunks = chunk_text(text, chunk_size=200, overlap=20)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 200 for chunk in chunks))
        self.assertIn('alpha', chunks[0])

    def test_score_chunk_prefers_matching_terms(self):
        question = 'printer toner replacement'
        relevant = 'Printer toner replacement steps for the office printer.'
        irrelevant = 'Quarterly sales and marketing plan.'
        self.assertGreater(score_chunk(question, relevant), score_chunk(question, irrelevant))

    def test_empty_text_has_no_chunks(self):
        self.assertEqual(chunk_text('   \n  '), [])


if __name__ == '__main__':
    unittest.main()
