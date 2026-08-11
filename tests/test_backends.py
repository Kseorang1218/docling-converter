import unittest
from pathlib import Path

from docling_core.types.doc import (
    ContentLayer,
    DocItemLabel,
    DoclingDocument,
    ImageRef,
    ImageRefMode,
    Size,
)

from doclings.docling_backend import (
    _export_markdown,
    _save_picture_images,
    broken_formula_span,
)
from doclings.mineru_backend import append_page_footnotes, markdown_title


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

    def test_docling_export_includes_page_footer_but_not_page_header(self):
        document = DoclingDocument(name="test")
        document.add_text(label=DocItemLabel.TEXT, text="Paper body")
        document.add_text(
            label=DocItemLabel.PAGE_HEADER,
            text="Repeated journal header",
            content_layer=ContentLayer.FURNITURE,
        )
        document.add_text(
            label=DocItemLabel.PAGE_FOOTER,
            text="Code: https://github.com/example/project",
            content_layer=ContentLayer.FURNITURE,
        )

        markdown = _export_markdown(document)

        self.assertIn("Paper body", markdown)
        self.assertIn("https://github.com/example/project", markdown)
        self.assertNotIn("Repeated journal header", markdown)


class MinerUTitleTests(unittest.TestCase):
    def test_extracts_first_markdown_heading(self):
        self.assertEqual(markdown_title("\n\n# Paper title\nbody"), "Paper title")

    def test_does_not_treat_plain_text_as_heading(self):
        self.assertIsNone(markdown_title("Paper title\nbody"))

    def test_skips_leading_journal_badge_line(self):
        content = "FOCUS\n\n# One-class classifiers with incremental learning\n\nbody"
        self.assertEqual(
            markdown_title(content),
            "One-class classifiers with incremental learning",
        )

    def test_gives_up_if_no_heading_within_search_window(self):
        content = "\n".join(["plain line"] * 10 + ["# Too far down title"])
        self.assertIsNone(markdown_title(content))


class MinerUPostprocessTests(unittest.TestCase):
    def test_appends_discarded_page_footnote_and_link_footer(self):
        content_list = [
            {
                "type": "page_footnote",
                "text": "Equal contribution.",
                "page_idx": 0,
            },
            {
                "type": "footer",
                "text": "Code: https://github.com/example/project",
                "page_idx": 1,
            },
        ]

        markdown, count = append_page_footnotes("# Paper\n\nBody", content_list)

        self.assertEqual(count, 2)
        self.assertIn("## Page footnotes", markdown)
        self.assertIn("- Page 1: Equal contribution.", markdown)
        self.assertIn(
            "- Page 2: Code: https://github.com/example/project", markdown
        )

    def test_ignores_headers_page_numbers_and_plain_footers(self):
        content_list = [
            {"type": "header", "text": "Journal title", "page_idx": 0},
            {"type": "page_number", "text": "42", "page_idx": 0},
            {"type": "footer", "text": "VOLUME 14.2026", "page_idx": 0},
        ]

        markdown, count = append_page_footnotes("# Paper", content_list)

        self.assertEqual(count, 0)
        self.assertEqual(markdown, "# Paper")

    def test_does_not_duplicate_note_already_present_in_markdown(self):
        existing = "# Paper\n\n1) Project code is available online."
        content_list = [
            {
                "type": "page_footnote",
                "text": "Project code is available online.",
                "page_idx": 0,
            }
        ]

        markdown, count = append_page_footnotes(existing, content_list)

        self.assertEqual(count, 0)
        self.assertEqual(markdown, existing)


if __name__ == "__main__":
    unittest.main()
