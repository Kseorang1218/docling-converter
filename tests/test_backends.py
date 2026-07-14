import unittest
from pathlib import Path

from docling_core.types.doc import DoclingDocument, ImageRef, ImageRefMode, Size

from doclings.docling_backend import (
    _save_picture_images,
    broken_formula_span,
)
from doclings.mineru_backend import markdown_title


class DoclingPostprocessTests(unittest.TestCase):
    def test_detects_runaway_ampersands_only(self):
        text = "prefix " + "& " * 8 + "suffix"
        span = broken_formula_span(text)
        self.assertIsNotNone(span)
        self.assertEqual(text[slice(*span)].replace(" ", ""), "&" * 8)

    def test_short_formula_is_preserved(self):
        self.assertIsNone(broken_formula_span(r"a &= b \\ c &= d"))

    def test_long_formula_without_runaway_pattern_is_preserved(self):
        self.assertIsNone(broken_formula_span("x" * 5000))

    def test_saved_picture_gets_relative_markdown_uri(self):
        class FakePilImage:
            def __init__(self):
                self.saved = None

            def save(self, path, image_format):
                self.saved = (path, image_format)

        class FakeImage:
            def __init__(self):
                self.pil_image = FakePilImage()
                self.uri = None

        image = FakeImage()
        document = type(
            "FakeDocument",
            (),
            {"pictures": [type("FakePicture", (), {"image": image})()]},
        )()

        count = _save_picture_images(document, Path("stage"), "Paper")

        self.assertEqual(count, 1)
        self.assertEqual(image.uri, Path("Paper_img_1.png"))
        self.assertEqual(image.pil_image.saved, (Path("stage/Paper_img_1.png"), "PNG"))

    def test_docling_serializer_emits_referenced_image_link(self):
        document = DoclingDocument(name="test")
        document.add_picture(
            image=ImageRef(
                mimetype="image/png",
                dpi=72,
                size=Size(width=1, height=1),
                uri=Path("Paper_img_1.png"),
            )
        )

        markdown = document.export_to_markdown(image_mode=ImageRefMode.REFERENCED)

        self.assertEqual(markdown, "![Image](Paper_img_1.png)")


class MinerUTitleTests(unittest.TestCase):
    def test_extracts_first_markdown_heading(self):
        self.assertEqual(markdown_title("\n\n# Paper title\nbody"), "Paper title")

    def test_does_not_treat_plain_text_as_heading(self):
        self.assertIsNone(markdown_title("Paper title\nbody"))


if __name__ == "__main__":
    unittest.main()
