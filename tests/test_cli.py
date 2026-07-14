import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from doclings.cli import main
from doclings.errors import ConversionError


class CliTests(unittest.TestCase):
    def test_missing_input_returns_failure(self):
        self.assertEqual(main(["/definitely/not/here.pdf"]), 1)

    def test_backend_failure_returns_failure_and_removes_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "paper.pdf"
            source.write_bytes(b"pdf")
            output = root / "results"

            with patch(
                "doclings.cli.convert_with_docling",
                side_effect=ConversionError("failed"),
            ):
                status = main([str(source), "-o", str(output)])

            self.assertEqual(status, 1)
            self.assertFalse(any(output.glob(".doclings-stage-*")))

    def test_success_publishes_backend_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "paper.pdf"
            source.write_bytes(b"pdf")
            output = root / "results"

            def fake_convert(_source, stage, _lang):
                (stage / "Paper.md").write_text("converted", encoding="utf-8")
                return "Paper"

            with patch("doclings.cli.convert_with_docling", side_effect=fake_convert):
                status = main([str(source), "-o", str(output)])

            self.assertEqual(status, 0)
            self.assertEqual(
                (output / "Paper" / "Paper.md").read_text(encoding="utf-8"),
                "converted",
            )


if __name__ == "__main__":
    unittest.main()
