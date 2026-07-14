import unittest
from pathlib import Path

from doclings.naming import MAX_FILENAME_BYTES, document_name, sanitize_title


class NamingTests(unittest.TestCase):
    def test_sanitize_title_replaces_invalid_characters(self):
        self.assertEqual(sanitize_title('  a/b:*?"<>|\n c  '), "a_b________ c")

    def test_sanitize_title_limits_utf8_bytes_without_splitting_character(self):
        title = sanitize_title("한" * 100)
        self.assertIsNotNone(title)
        self.assertLessEqual(len(title.encode("utf-8")), MAX_FILENAME_BYTES)
        self.assertEqual(title, "한" * 50)

    def test_sanitize_title_avoids_windows_reserved_name(self):
        self.assertEqual(sanitize_title("CON.txt"), "_CON.txt")

    def test_document_name_sanitizes_input_stem_fallback(self):
        self.assertEqual(document_name(None, Path("bad:name.pdf")), "bad_name")


if __name__ == "__main__":
    unittest.main()
