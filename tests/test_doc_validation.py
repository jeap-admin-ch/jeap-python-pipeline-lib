import unittest
from unittest.mock import patch

from jeap_pipeline.doc_content_validation import (ContentFinding, ContentFindingCode, ContentReport)
from jeap_pipeline.doc_diagram_sources import (DiagramFinding, DiagramFindingCode, DiagramReport)
from jeap_pipeline.doc_path_tree import DocumentationPathError
from jeap_pipeline.doc_service_operations import (DocumentationSet, StructureFinding,
                                                  StructureReport)
from jeap_pipeline.doc_validation import validate_documentation_sets

MARKDOWN_SET = DocumentationSet(path="./docs", type="system-docs", system="orders", template="arc42",
                                source_format="markdown")

HTML_SET = DocumentationSet(path="./html-docs/configuration-reference", type="component-docs",
                            system="orders", component="foo-bar-scs", template="arc42",
                            source_format="html", location="8-crosscutting-concepts",
                            topic="configuration-reference", label="Configuration Reference")

ACCEPTED_STRUCTURE = StructureReport(accepted=True, template="arc42", paths_checked=17,
                                     paths_ignored=1, allowed_folders=["1-intro"],
                                     allowed_extensions=["md"])

REJECTED_STRUCTURE = StructureReport(
    accepted=False, template="arc42", paths_checked=17, paths_ignored=2,
    allowed_folders=["1-intro", "6-runtime-view"], allowed_extensions=["md", "png"],
    findings=[
        StructureFinding(code="UNKNOWN_CHAPTER", path="4-runtime-view/reactions.md",
                         message="'4-runtime-view' is not a chapter of arc42. Did you mean "
                                 "'6-runtime-view'?"),
        StructureFinding(code="EMPTY_TREE", message="Nothing in the set would be published."),
    ])

ACCEPTED_CONTENT = ContentReport(files_checked=17)

REJECTED_CONTENT = ContentReport(files_checked=17, findings=[
    ContentFinding(ContentFindingCode.FORBIDDEN_FRONT_MATTER_KEY, "1-intro/goals.md",
                   "'slug' is not allowed in front matter.", 3),
])

NO_DIAGRAMS = DiagramReport(pairs_checked=0)

ACCEPTED_DIAGRAMS = DiagramReport(pairs_checked=2)

REJECTED_DIAGRAMS = DiagramReport(pairs_checked=2, findings=[
    DiagramFinding(DiagramFindingCode.STALE_DIAGRAM_IMAGE, path="images/overview.drawio",
                   message="'images/overview.drawio' was changed after "
                           "'images/overview.svg' was exported from it."),
])


class ValidateDocumentationSetsTestCase(unittest.TestCase):
    """The orchestration, with everything it collaborates with stubbed."""

    def setUp(self):
        self.token = patch("jeap_pipeline.doc_validation.fetch_client_credentials_token",
                           return_value="a-token").start()
        self.paths = patch("jeap_pipeline.doc_validation.collect_documentation_paths",
                           return_value=["1-intro/goals.md"]).start()
        self.content = patch("jeap_pipeline.doc_validation.validate_documentation_content",
                             return_value=ACCEPTED_CONTENT).start()
        self.structure = patch("jeap_pipeline.doc_validation.validate_documentation_structure",
                               return_value=ACCEPTED_STRUCTURE).start()
        self.diagrams = patch("jeap_pipeline.doc_validation.check_diagram_sources",
                              return_value=NO_DIAGRAMS).start()
        self.addCleanup(patch.stopall)

    def validate(self, *documentation_sets, **kwargs):
        return validate_documentation_sets(
            list(documentation_sets) or [MARKDOWN_SET],
            kwargs.pop("doc_service_url", "https://docs.example.ch"),
            kwargs.pop("token_uri", "https://auth.example.ch/oauth2/token"),
            kwargs.pop("client_id", "orders-doc-pipeline"),
            kwargs.pop("client_secret", "a-secret"),
            **kwargs)


class OrchestrationTest(ValidateDocumentationSetsTestCase):

    def test_one_token_is_fetched_for_every_set(self):
        self.validate(MARKDOWN_SET, HTML_SET)

        self.assertEqual(1, self.token.call_count)
        self.token.assert_called_once_with("https://auth.example.ch/oauth2/token",
                                           "orders-doc-pipeline", "a-secret")
        self.assertEqual(2, self.structure.call_count)

    def test_a_markdown_set_is_content_checked(self):
        outcome = self.validate(MARKDOWN_SET)

        self.assertEqual(1, self.content.call_count)
        self.assertIsNotNone(outcome.sets[0].content)

    def test_an_html_set_is_not_content_checked(self):
        outcome = self.validate(HTML_SET)

        self.assertEqual(0, self.content.call_count)
        self.assertIsNone(outcome.sets[0].content)
        self.assertEqual(1, self.structure.call_count)

    def test_the_path_of_a_set_is_resolved_against_the_working_directory(self):
        self.validate(MARKDOWN_SET, working_directory="/home/runner/work/repo")

        self.paths.assert_called_once_with("/home/runner/work/repo/docs",
                                          keep_diagram_sources=True)

    def test_the_path_of_a_set_is_relative_to_the_checkout_by_default(self):
        self.validate(MARKDOWN_SET)

        self.paths.assert_called_once_with("docs", keep_diagram_sources=True)

    def test_both_checks_run_even_when_the_first_finds_something(self):
        self.content.return_value = REJECTED_CONTENT

        outcome = self.validate(MARKDOWN_SET)

        self.assertEqual(1, self.structure.call_count, "the structure is asked anyway")
        self.assertFalse(outcome.accepted)

    def test_a_set_is_accepted_only_when_both_checks_are(self):
        self.assertTrue(self.validate(MARKDOWN_SET).accepted)

        self.content.return_value = REJECTED_CONTENT
        self.assertFalse(self.validate(MARKDOWN_SET).accepted)

        self.content.return_value = ACCEPTED_CONTENT
        self.structure.return_value = REJECTED_STRUCTURE
        self.assertFalse(self.validate(MARKDOWN_SET).accepted)

    def test_one_rejected_set_of_two_rejects_the_whole_run(self):
        self.structure.side_effect = [ACCEPTED_STRUCTURE, REJECTED_STRUCTURE]

        outcome = self.validate(MARKDOWN_SET, HTML_SET)

        self.assertFalse(outcome.accepted)
        self.assertEqual(1, outcome.rejected_sets)

    def test_a_missing_documentation_folder_is_not_swallowed(self):
        self.paths.side_effect = DocumentationPathError("The documentation folder is missing.")

        with self.assertRaises(DocumentationPathError):
            self.validate(MARKDOWN_SET)


class DiagramTest(ValidateDocumentationSetsTestCase):
    """The diagram responsibility, as the orchestration sees it."""

    def test_the_diagrams_of_a_set_are_checked_whatever_its_source_format(self):
        # An HTML set is not content-checked, but its diagrams are kept the same way a Markdown
        # set's are, so the export can go stale there just as easily.
        self.validate(MARKDOWN_SET, HTML_SET)

        self.assertEqual(2, self.diagrams.call_count)

    def test_a_stale_diagram_rejects_the_set_on_its_own(self):
        self.diagrams.return_value = REJECTED_DIAGRAMS

        outcome = self.validate(MARKDOWN_SET)

        self.assertFalse(outcome.accepted)
        self.assertEqual(1, self.structure.call_count, "the structure is asked anyway")

    def test_the_tree_is_walked_once_with_the_sources_and_the_upload_list_derived_from_it(self):
        # Walking twice - once for the check, once for the upload - could answer differently, and
        # then the set that was validated would not be the set that is sent.
        self.paths.return_value = ["architecture.md",
                                   "images/overview.drawio", "images/overview.svg"]

        self.validate(MARKDOWN_SET)

        self.assertEqual(1, self.paths.call_count)
        self.diagrams.assert_called_once_with(
            "docs",
            ["architecture.md", "images/overview.drawio", "images/overview.svg"],
            deepen=False, source_format="markdown")
        self.assertEqual(["architecture.md", "images/overview.svg"],
                         self.structure.call_args.args[3],
                         "the doc service is asked about the set without the editor files")

    def test_the_diagram_check_may_be_told_it_can_deepen_the_history(self):
        self.validate(MARKDOWN_SET, deepen_diagram_history=True)

        self.assertTrue(self.diagrams.call_args.kwargs["deepen"])


class FindingsTest(ValidateDocumentationSetsTestCase):

    def test_the_findings_of_every_responsibility_are_flattened(self):
        self.diagrams.return_value = REJECTED_DIAGRAMS
        self.content.return_value = REJECTED_CONTENT
        self.structure.return_value = REJECTED_STRUCTURE

        findings = self.validate(MARKDOWN_SET).findings

        self.assertEqual(["diagrams", "content", "structure", "structure"],
                         [finding.location for finding in findings])
        self.assertEqual(["STALE_DIAGRAM_IMAGE", "FORBIDDEN_FRONT_MATTER_KEY", "UNKNOWN_CHAPTER",
                          "EMPTY_TREE"],
                         [finding.code for finding in findings])

    def test_a_diagram_finding_names_the_source_as_the_repository_sees_it(self):
        self.diagrams.return_value = REJECTED_DIAGRAMS

        finding = self.validate(MARKDOWN_SET).findings[0]

        self.assertEqual("images/overview.drawio", finding.path)
        self.assertEqual("docs/images/overview.drawio", finding.repository_path)

    def test_a_finding_names_the_path_as_the_repository_sees_it(self):
        self.content.return_value = REJECTED_CONTENT

        finding = self.validate(MARKDOWN_SET).findings[0]

        self.assertEqual("1-intro/goals.md", finding.path)
        self.assertEqual("docs/1-intro/goals.md", finding.repository_path)
        self.assertEqual(3, finding.line)

    def test_a_set_level_finding_has_no_path(self):
        self.structure.return_value = REJECTED_STRUCTURE

        empty_tree = [finding for finding in self.validate(MARKDOWN_SET).findings
                      if finding.code == "EMPTY_TREE"][0]

        self.assertIsNone(empty_tree.path)
        self.assertIsNone(empty_tree.repository_path)


class ReportTest(ValidateDocumentationSetsTestCase):

    def test_an_accepted_run_reports_one_line_per_set(self):
        report = self.validate(MARKDOWN_SET).report

        self.assertIn("Validating ./docs (system-docs, orders, arc42, markdown)", report)
        self.assertIn("17 file(s) checked, 1 path(s), 1 ignored - content OK, structure OK", report)
        self.assertIn("Documentation validation passed: 1 documentation set(s).", report)

    def test_an_accepted_html_set_does_not_claim_a_content_check(self):
        report = self.validate(HTML_SET).report

        self.assertNotIn("content OK", report)
        self.assertIn("structure OK", report)

    def test_an_accepted_set_with_diagrams_says_how_many_were_checked(self):
        self.diagrams.return_value = ACCEPTED_DIAGRAMS

        report = self.validate(MARKDOWN_SET).report

        self.assertIn("content OK, 2 diagram(s) OK, structure OK", report)

    def test_an_accepted_set_without_diagrams_does_not_mention_them(self):
        report = self.validate(MARKDOWN_SET).report

        self.assertNotIn("diagram", report)

    def test_an_uncommitted_diagram_is_counted_out_of_what_was_checked(self):
        self.diagrams.return_value = DiagramReport(pairs_checked=2, pairs_uncommitted=1)

        report = self.validate(MARKDOWN_SET).report

        self.assertIn("1 of 2 diagram(s) OK", report)

    def test_a_stale_diagram_is_printed_before_the_other_responsibilities(self):
        # The fix for a stale export is not in the file the content and structure findings point
        # at, so it has to be the first thing read.
        self.diagrams.return_value = REJECTED_DIAGRAMS
        self.content.return_value = REJECTED_CONTENT
        self.structure.return_value = REJECTED_STRUCTURE

        report = self.validate(MARKDOWN_SET).report

        self.assertIn("Diagrams: 1 problem(s) in 2 diagram(s).", report)
        self.assertIn("STALE_DIAGRAM_IMAGE", report)
        self.assertLess(report.index("Diagrams:"), report.index("Content:"))
        self.assertIn("Documentation validation failed: 4 problem(s) in 1 of 1 documentation "
                      "set(s).", report)

    def test_an_undatable_history_is_reported_against_the_whole_set(self):
        self.diagrams.return_value = DiagramReport(pairs_checked=1, findings=[
            DiagramFinding(DiagramFindingCode.UNDATABLE_DIAGRAM_HISTORY,
                           message="The history of the checkout does not reach back far enough.")])

        report = self.validate(MARKDOWN_SET).report

        self.assertIn("(the documentation set)", report)
        self.assertIn("UNDATABLE_DIAGRAM_HISTORY", report)

    def test_a_rejected_run_prints_both_responsibilities_and_what_is_allowed(self):
        self.content.return_value = REJECTED_CONTENT
        self.structure.return_value = REJECTED_STRUCTURE

        report = self.validate(MARKDOWN_SET).report

        self.assertIn("Content: 1 problem(s) in 17 file(s).", report)
        self.assertIn("1-intro/goals.md:3", report)
        self.assertIn("FORBIDDEN_FRONT_MATTER_KEY", report)
        self.assertIn("Structure: 2 problem(s) in 17 path(s), 2 ignored.", report)
        self.assertIn("UNKNOWN_CHAPTER", report)
        self.assertIn("Folders:    1-intro, 6-runtime-view", report)
        self.assertIn("Extensions: .md, .png", report)
        self.assertIn("Documentation validation failed: 3 problem(s) in 1 of 1 documentation "
                      "set(s).", report)

    def test_a_set_level_finding_is_printed_before_the_ones_with_a_path(self):
        self.structure.return_value = REJECTED_STRUCTURE

        report = self.validate(MARKDOWN_SET).report

        self.assertLess(report.index("(the documentation set)"),
                        report.index("4-runtime-view/reactions.md"))

    def test_a_capped_report_says_how_many_it_left_out(self):
        self.content.return_value = ContentReport(files_checked=3, findings=REJECTED_CONTENT.findings,
                                                  findings_omitted=7)

        report = self.validate(MARKDOWN_SET).report

        self.assertIn("Content: 1 of 8 problem(s) in 3 file(s).", report)
        self.assertIn("… and 7 more, not listed.", report)

    def test_a_finding_code_wider_than_the_column_keeps_its_distance(self):
        # The codes are the doc service's API and it may add one; a code that ran into its message
        # would make the report of a newer doc service unreadable.
        code = "A_FINDING_CODE_FROM_A_NEWER_DOC_SERVICE"
        self.structure.return_value = StructureReport(
            accepted=False, template="arc42", paths_checked=1,
            findings=[StructureFinding(code=code, path="1-intro/goals.md", message="A message.")])

        report = self.validate(MARKDOWN_SET).report

        self.assertIn(f"{code}  A message.", report)

    def test_the_report_of_a_set_is_kept_on_the_set(self):
        outcome = self.validate(MARKDOWN_SET, HTML_SET)

        self.assertIn("./docs", outcome.sets[0].report)
        self.assertIn("configuration-reference", outcome.sets[1].report)
        self.assertIn(outcome.sets[0].report, outcome.report)


if __name__ == "__main__":
    unittest.main()
