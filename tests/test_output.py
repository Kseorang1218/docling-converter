import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from doclings.errors import ConversionError
from doclings.output import (
    MANIFEST_FILENAME,
    SourceIdentity,
    publish_directory,
    staging_directory,
)


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def _identity(self, digest: str = "a" * 64) -> SourceIdentity:
        return SourceIdentity(name="paper.pdf", sha256=digest)

    def _stage(self, content: str = "new") -> Path:
        stage = self.root / f"stage-{content}"
        stage.mkdir()
        (stage / "Paper.md").write_text(content, encoding="utf-8")
        return stage

    def test_publish_writes_manifest_and_moves_completed_stage(self):
        stage = self._stage()
        target = publish_directory(
            stage, self.root, "Paper", self._identity(), "docling"
        )

        self.assertEqual(target, self.root / "Paper")
        self.assertFalse(stage.exists())
        manifest = json.loads((target / MANIFEST_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(manifest["source"]["sha256"], "a" * 64)
        self.assertEqual(manifest["backend"], "docling")

    def test_title_collision_preserves_legacy_output(self):
        legacy = self.root / "Paper"
        legacy.mkdir()
        (legacy / "old.md").write_text("old", encoding="utf-8")

        target = publish_directory(
            self._stage(), self.root, "Paper", self._identity(), "docling"
        )

        self.assertEqual(target, self.root / "Paper--aaaaaaaa")
        self.assertEqual((legacy / "old.md").read_text(encoding="utf-8"), "old")

    def test_same_source_replaces_previous_result(self):
        first = publish_directory(
            self._stage("first"), self.root, "Paper", self._identity(), "docling"
        )
        second = publish_directory(
            self._stage("second"), self.root, "Paper", self._identity(), "mineru"
        )

        self.assertEqual(first, second)
        self.assertEqual((second / "Paper.md").read_text(encoding="utf-8"), "second")
        self.assertFalse(any(self.root.glob(".*.backup-*")))

    def test_failed_swap_restores_previous_result(self):
        target = publish_directory(
            self._stage("first"), self.root, "Paper", self._identity(), "docling"
        )
        new_stage = self._stage("second")
        real_replace = os.replace
        call_count = 0

        def fail_second_replace(source, destination):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise OSError("simulated swap failure")
            return real_replace(source, destination)

        with patch("doclings.output.os.replace", side_effect=fail_second_replace):
            with self.assertRaisesRegex(OSError, "simulated swap failure"):
                publish_directory(
                    new_stage, self.root, "Paper", self._identity(), "docling"
                )

        self.assertEqual((target / "Paper.md").read_text(encoding="utf-8"), "first")
        self.assertFalse(any(self.root.glob(".*.backup-*")))

    def test_staging_directory_cleans_up_after_failure(self):
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with staging_directory(self.root) as stage:
                (stage / "partial").write_text("x", encoding="utf-8")
                raise RuntimeError("boom")
        self.assertFalse(any(self.root.glob(".doclings-stage-*")))

    def test_refuses_to_replace_directory_containing_input(self):
        source_dir = self.root / "Paper"
        source_dir.mkdir()
        source = source_dir / "paper.pdf"
        source.write_bytes(b"pdf")
        identity = SourceIdentity.from_path(source)

        with self.assertRaisesRegex(ConversionError, "contains the input PDF"):
            publish_directory(
                self._stage(),
                self.root,
                "Paper",
                identity,
                "docling",
                overwrite=True,
            )
        self.assertTrue(source.exists())


if __name__ == "__main__":
    unittest.main()
