import os
import unittest

from tempfile import TemporaryDirectory

from jeap_pipeline.doc_content_validation import (ContentFindingCode,
                                                  validate_documentation_content)


class ContentValidationTestCase(unittest.TestCase):
    """A documentation set written into a temporary folder, and validated as a whole."""

    def setUp(self):
        self._directory = TemporaryDirectory()
        self.root = self._directory.name

    def tearDown(self):
        self._directory.cleanup()

    def write(self, relative_path, content, encoding="utf-8"):
        absolute = os.path.join(self.root, relative_path)
        os.makedirs(os.path.dirname(absolute), exist_ok=True)
        mode, payload = ("wb", content) if isinstance(content, bytes) else ("w", content)
        with open(absolute, mode) as target:
            if mode == "wb":
                target.write(payload)
            else:
                target.write(payload)
        return relative_path

    def validate(self, *paths, **kwargs):
        return validate_documentation_content(self.root, list(paths), **kwargs)

    def codes(self, report):
        return [str(finding.code) for finding in report.findings]


class ValidPagesTest(ContentValidationTestCase):

    def test_a_page_with_title_and_description_and_a_resolving_link_is_accepted(self):
        self.write("1-intro/goals.md",
                   "---\ntitle: Goals\ndescription: What this is for.\n---\n\n"
                   "See [the constraints](../2-constraints/platform.md).\n")
        self.write("2-constraints/platform.md", "---\ntitle: Platform\n---\n")

        report = self.validate("1-intro/goals.md", "2-constraints/platform.md")

        self.assertTrue(report.accepted)
        self.assertEqual(2, report.files_checked)

    def test_the_allowed_front_matter_keys_are_accepted(self):
        self.write("1-intro/goals.md",
                   "---\ntitle: Goals\ndescription: d\nsidebar_label: Goals\n"
                   "tags: [architecture]\nkeywords: [arc42]\n---\n")

        self.assertTrue(self.validate("1-intro/goals.md").accepted)

    def test_a_page_without_front_matter_is_accepted(self):
        self.write("1-intro/goals.md", "# Goals\n\nText.\n")

        self.assertTrue(self.validate("1-intro/goals.md").accepted)

    def test_an_image_beside_its_page_is_accepted(self):
        self.write("5-building-block-view/design.md", "![Overview](overview.png)\n")
        self.write("5-building-block-view/overview.png", "png")

        report = self.validate("5-building-block-view/design.md",
                               "5-building-block-view/overview.png")

        self.assertTrue(report.accepted)
        self.assertEqual(1, report.files_checked, "only Markdown is read")

    def test_only_markdown_is_read(self):
        self.write("5-building-block-view/notes.txt", "[dead](nowhere.md)")

        report = self.validate("5-building-block-view/notes.txt")

        self.assertTrue(report.accepted)
        self.assertEqual(0, report.files_checked)


class FrontMatterTest(ContentValidationTestCase):

    def test_slug_is_refused_and_the_message_says_why(self):
        self.write("1-intro/goals.md", "---\ntitle: Goals\nslug: /\n---\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([str(ContentFindingCode.FORBIDDEN_FRONT_MATTER_KEY)], self.codes(report))
        finding = report.findings[0]
        self.assertIn("'slug' is not allowed", finding.message)
        self.assertIn("URL", finding.message)
        self.assertIn("Allowed: description, keywords, sidebar_label, tags, title.",
                      finding.message)
        self.assertEqual(3, finding.line, "the line the key is written on, fence included")

    def test_sidebar_position_is_refused(self):
        self.write("1-intro/goals.md", "---\ntitle: Goals\nsidebar_position: 2\n---\n")

        self.assertEqual([str(ContentFindingCode.FORBIDDEN_FRONT_MATTER_KEY)],
                         self.codes(self.validate("1-intro/goals.md")))

    def test_every_refused_key_is_its_own_finding(self):
        self.write("1-intro/goals.md", "---\nslug: /a\nid: goals\ndraft: true\n---\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual(3, len(report.findings))
        self.assertEqual(["draft", "id", "slug"],
                         sorted(finding.message.split("'")[1] for finding in report.findings))

    def test_an_unterminated_front_matter_block_is_reported(self):
        self.write("1-intro/goals.md", "---\ntitle: Goals\n\n# Goals\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([str(ContentFindingCode.MALFORMED_FRONT_MATTER)], self.codes(report))
        self.assertIn("never closed", report.findings[0].message)

    def test_front_matter_that_is_not_a_mapping_is_reported(self):
        self.write("1-intro/goals.md", "---\n- Goals\n- More goals\n---\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([str(ContentFindingCode.MALFORMED_FRONT_MATTER)], self.codes(report))
        self.assertIn("not a mapping", report.findings[0].message)

    def test_front_matter_that_is_not_yaml_is_reported(self):
        self.write("1-intro/goals.md", "---\ntitle: [unclosed\n---\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([str(ContentFindingCode.MALFORMED_FRONT_MATTER)], self.codes(report))
        self.assertIn("not valid YAML", report.findings[0].message)

    def test_a_key_written_twice_is_reported(self):
        # yaml keeps the last of the two without a word; the parser the site is built with does not.
        self.write("1-intro/goals.md", "---\ntitle: One\ntitle: Two\n---\n\nText.\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([ContentFindingCode.MALFORMED_FRONT_MATTER],
                         [finding.code for finding in report.findings])
        self.assertIn("written twice", report.findings[0].message)

    def test_an_empty_front_matter_block_is_accepted(self):
        self.write("1-intro/goals.md", "---\n---\n\n# Goals\n")

        self.assertTrue(self.validate("1-intro/goals.md").accepted)


class LinkTest(ContentValidationTestCase):

    def test_a_link_to_a_file_that_is_not_in_the_set_is_dead(self):
        self.write("1-intro/goals.md", "See [the whitebox view](../5-building-block-view/whitebox-view.md).\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([str(ContentFindingCode.DEAD_LINK)], self.codes(report))
        self.assertIn("whitebox-view.md", report.findings[0].message)
        self.assertEqual(1, report.findings[0].line)

    def test_a_link_without_the_extension_names_the_extension(self):
        self.write("1-intro/goals.md", "See [the platform](../2-constraints/platform).\n")
        self.write("2-constraints/platform.md", "---\ntitle: Platform\n---\n")

        report = self.validate("1-intro/goals.md", "2-constraints/platform.md")

        self.assertEqual([str(ContentFindingCode.LINK_WITHOUT_EXTENSION)], self.codes(report))
        self.assertIn("'.md'", report.findings[0].message)

    def test_a_link_leaving_the_documentation_folder_is_reported_as_such(self):
        self.write("1-intro/goals.md", "See [the code](../../src/main/java/Main.java).\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([str(ContentFindingCode.LINK_OUT_OF_SET)], self.codes(report))
        self.assertIn("outside the documentation folder", report.findings[0].message)

    def test_a_missing_image_is_reported(self):
        self.write("5-building-block-view/design.md", "![Overview](overview.png)\n")

        report = self.validate("5-building-block-view/design.md")

        self.assertEqual([str(ContentFindingCode.DEAD_LINK)], self.codes(report))
        self.assertIn("image", report.findings[0].message)

    def test_http_and_mailto_links_are_not_checked(self):
        self.write("1-intro/goals.md",
                   "[a](https://example.ch/x) [b](http://example.ch) [c](mailto:x@example.ch)\n")

        self.assertTrue(self.validate("1-intro/goals.md").accepted)

    def test_a_site_absolute_link_is_not_checked(self):
        self.write("1-intro/goals.md", "[the generated view](/systems/jme/system-architecture/)\n")

        self.assertTrue(self.validate("1-intro/goals.md").accepted)

    def test_an_anchor_only_link_is_not_checked(self):
        self.write("1-intro/goals.md", "[below](#the-goals)\n\n## The goals\n")

        self.assertTrue(self.validate("1-intro/goals.md").accepted)

    def test_an_anchor_on_a_resolving_link_is_accepted(self):
        self.write("1-intro/goals.md", "[there](../2-constraints/platform.md#aws)\n")
        self.write("2-constraints/platform.md", "## AWS\n")

        self.assertTrue(self.validate("1-intro/goals.md", "2-constraints/platform.md").accepted)

    def test_a_percent_encoded_target_is_resolved(self):
        self.write("1-intro/goals.md", "[there](../2-constraints/a%20page.md)\n")
        self.write("2-constraints/a page.md", "# A page\n")

        self.assertTrue(self.validate("1-intro/goals.md", "2-constraints/a page.md").accepted)

    def test_a_link_inside_a_fenced_code_block_is_not_a_link(self):
        self.write("1-intro/goals.md", "```\n[dead](nowhere.md)\n```\n")

        self.assertTrue(self.validate("1-intro/goals.md").accepted)

    def test_a_link_in_an_inline_code_span_is_not_a_link(self):
        self.write("1-intro/goals.md", "Write `[dead](nowhere.md)` to link a page.\n")

        self.assertTrue(self.validate("1-intro/goals.md").accepted)

    def test_the_line_of_a_finding_counts_the_front_matter(self):
        self.write("1-intro/goals.md",
                   "---\ntitle: Goals\n---\n\n# Goals\n\nSee [nothing](nowhere.md).\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual(7, report.findings[0].line)

    def test_the_line_is_the_link_and_not_the_paragraph_it_stands_in(self):
        self.write("1-intro/goals.md",
                   "The view is in the [deployment chapter](gone.md),\n"
                   "and the terms are in the [glossary](also-gone.md).\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([1, 2], [finding.line for finding in report.findings])

    def test_the_line_of_a_link_in_a_table_row_is_that_row(self):
        self.write("1-intro/goals.md",
                   "| Page                | Note |\n"
                   "| ------------------- | ---- |\n"
                   "| [one](gone.md)      | a    |\n"
                   "| [two](also-gone.md) | b    |\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([3, 4], [finding.line for finding in report.findings])

    def test_one_target_linked_twice_is_reported_on_both_lines(self):
        self.write("1-intro/goals.md",
                   "First [a link](gone.md),\n"
                   "and again [the same link](gone.md).\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([1, 2], [finding.line for finding in report.findings])

    def test_the_line_of_a_link_in_a_list_item_is_that_item(self):
        self.write("1-intro/goals.md", "- one\n- two\n- [three](gone.md)\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([3], [finding.line for finding in report.findings])

    def test_a_target_written_nowhere_in_its_block_falls_back_to_the_block(self):
        # A reference link carries its target in a definition of its own, so the target is not in
        # the source of the paragraph; the finding then names the line the paragraph starts on.
        self.write("1-intro/goals.md",
                   "A paragraph\nwith [a page][somewhere] in it.\n\n[somewhere]: gone.md\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([ContentFindingCode.DEAD_LINK],
                         [finding.code for finding in report.findings])
        self.assertEqual(1, report.findings[0].line)


class EncodingTest(ContentValidationTestCase):

    def test_a_file_that_is_not_utf_8_is_reported(self):
        self.write("1-intro/goals.md", "Ziele: Übersicht\n".encode("latin-1"))

        report = self.validate("1-intro/goals.md")

        self.assertEqual([str(ContentFindingCode.INVALID_ENCODING)], self.codes(report))
        self.assertIn("UTF-8", report.findings[0].message)

    def test_a_file_with_a_nul_byte_is_reported(self):
        self.write("1-intro/goals.md", b"# Goals\n\x00\n")

        report = self.validate("1-intro/goals.md")

        self.assertEqual([str(ContentFindingCode.INVALID_ENCODING)], self.codes(report))
        self.assertIn("NUL", report.findings[0].message)


class ReportTest(ContentValidationTestCase):

    def test_the_findings_are_ordered_by_path_and_line(self):
        self.write("2-constraints/b.md", "[x](nowhere.md)\n")
        self.write("1-intro/a.md", "[x](nowhere.md)\n\n[y](nowhere-either.md)\n")

        report = self.validate("1-intro/a.md", "2-constraints/b.md")

        self.assertEqual([("1-intro/a.md", 1), ("1-intro/a.md", 3), ("2-constraints/b.md", 1)],
                         [(finding.path, finding.line) for finding in report.findings])

    def test_the_report_is_capped_and_says_how_many_it_left_out(self):
        self.write("1-intro/goals.md", "".join(f"[x{index}](nowhere{index}.md)\n\n"
                                               for index in range(10)))

        report = self.validate("1-intro/goals.md", max_findings=4)

        self.assertEqual(4, len(report.findings))
        self.assertEqual(6, report.findings_omitted)
        self.assertFalse(report.accepted)

    def test_a_custom_allowlist_is_applied(self):
        self.write("1-intro/goals.md", "---\ntitle: Goals\n---\n")

        report = self.validate("1-intro/goals.md",
                               allowed_front_matter_keys=frozenset({"description"}))

        self.assertEqual([str(ContentFindingCode.FORBIDDEN_FRONT_MATTER_KEY)], self.codes(report))


if __name__ == "__main__":
    unittest.main()
