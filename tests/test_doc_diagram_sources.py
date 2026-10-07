"""The diagram source/image pairing of `jeap_pipeline.doc_diagram_sources`.

The git cases build real repositories with real commits. Nothing about the dating is stubbed on
purpose: a date check is the kind of thing that keeps passing long after it has stopped working - a
shallow clone alone is enough to make every diagram look exactly as old as its image - so the only
test worth having is one that drives real history.
"""

import os
import subprocess
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from jeap_pipeline.doc_diagram_sources import (DiagramFindingCode, DiagramPair,
                                               check_diagram_sources, diagram_pairs_of,
                                               diagram_sources_of)


class PairingRuleTest(unittest.TestCase):
    """Which file is whose source - pure name analysis, no git and no file contents."""

    def test_a_file_extending_an_image_name_is_the_images_source(self):
        paths = ["architecture.md", "images/overview.drawio", "images/overview.svg"]

        self.assertEqual([DiagramPair(source="images/overview.drawio",
                                      image="images/overview.svg")],
                         diagram_pairs_of(paths))

    def test_a_source_with_a_double_extension_is_paired_with_its_image(self):
        # The shape the diagrams migrated from the Confluence draw.io plugin have.
        paths = ["images/flow.drawio.xml", "images/flow.png"]

        self.assertEqual([DiagramPair(source="images/flow.drawio.xml", image="images/flow.png")],
                         diagram_pairs_of(paths))

    def test_a_published_asset_next_to_an_image_is_not_a_source(self):
        # Dropping either of these would lose a real asset: both extensions are ones the doc
        # service publishes, so neither is an editor file nobody could open.
        paths = ["images/report.pdf", "images/report.svg",
                 "images/logo.png", "images/logo.svg",
                 "images/notes.txt", "images/notes.png"]

        self.assertEqual([], diagram_pairs_of(paths))

    def test_a_markdown_page_named_after_an_image_is_not_a_source(self):
        paths = ["overview.md", "overview.svg"]

        self.assertEqual([], diagram_pairs_of(paths))

    def test_the_pairing_is_per_folder(self):
        paths = ["images/overview.svg", "sources/overview.drawio"]

        self.assertEqual([], diagram_pairs_of(paths),
                         "the author put them in different folders on purpose")

    def test_a_source_needs_an_image_not_just_a_namesake(self):
        paths = ["images/overview.drawio", "images/overview.pdf"]

        self.assertEqual([], diagram_pairs_of(paths),
                         "a .pdf is not a picture an <img> tag can show")

    def test_the_most_specific_image_claims_a_source(self):
        paths = ["images/flow.svg", "images/flow.detail.svg", "images/flow.detail.drawio"]

        self.assertEqual([DiagramPair(source="images/flow.detail.drawio",
                                      image="images/flow.detail.svg")],
                         diagram_pairs_of(paths))

    def test_a_name_equal_to_the_image_stem_is_not_a_source(self):
        paths = ["images/overview.svg", "images/overview"]

        self.assertEqual([], diagram_pairs_of(paths), "the name has to EXTEND the stem")

    def test_an_extension_is_matched_case_insensitively(self):
        paths = ["images/overview.SVG", "images/overview.drawio"]

        self.assertEqual([DiagramPair(source="images/overview.drawio",
                                      image="images/overview.SVG")],
                         diagram_pairs_of(paths))

    def test_a_dotfile_is_never_a_source(self):
        paths = ["images/overview.svg", "images/.overview"]

        self.assertEqual([], diagram_pairs_of(paths))

    def test_a_diagram_at_the_root_of_the_set_is_found(self):
        paths = ["overview.drawio", "overview.svg"]

        self.assertEqual([DiagramPair(source="overview.drawio", image="overview.svg")],
                         diagram_pairs_of(paths))

    def test_the_sources_are_listed_sorted(self):
        paths = ["b/second.drawio", "b/second.svg", "a/first.drawio", "a/first.png"]

        self.assertEqual(["a/first.drawio", "b/second.drawio"], diagram_sources_of(paths))


class DocumentationSetFixture(unittest.TestCase):
    """A git repository whose `docs/` folder holds one diagram, with helpers to age it."""

    def setUp(self):
        self.workspace = TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.repository = os.path.join(self.workspace.name, "repository")
        self.root = os.path.join(self.repository, "docs")
        os.makedirs(os.path.join(self.root, "images"))
        self.write("architecture.md", "# Architecture\n\n![Overview](images/overview.svg)\n")
        self.write("images/overview.drawio", "<mxfile><diagram>v1</diagram></mxfile>\n")
        self.write("images/overview.svg", "<svg>v1</svg>\n")
        self.git("init", "-q", "-b", "main")
        self.commit("the diagram and its export")

    def write(self, relative_path, content):
        with open(os.path.join(self.root, relative_path), "w", encoding="utf-8") as handle:
            handle.write(content)

    def git(self, *arguments, repository=None):
        return subprocess.run(["git", "-C", repository or self.repository, *arguments],
                              capture_output=True, text=True, check=True)

    def commit(self, message, repository=None):
        self.git("add", "-A", repository=repository)
        self.git("-c", "user.email=t@example.org", "-c", "user.name=Test",
                 "commit", "-qm", message, repository=repository)

    def paths(self):
        """What `collect_documentation_paths(root, keep_diagram_sources=True)` would return."""
        found = []
        for directory, _, file_names in os.walk(self.root):
            for file_name in file_names:
                absolute = os.path.join(directory, file_name)
                found.append(os.path.relpath(absolute, self.root).replace(os.sep, "/"))
        return sorted(found)

    def edit_the_source_only(self):
        """The mistake the check exists for: the diagram changed, the image left as it was."""
        self.write("images/overview.drawio", "<mxfile><diagram>v2</diagram></mxfile>\n")
        self.commit("reworked the diagram")

    def add_history(self, commits):
        """Unrelated commits, so the diagram ends up beyond a depth-1 clone."""
        for number in range(commits):
            self.write("changelog.md", f"# Changelog\n\nentry {number}\n")
            self.commit(f"entry {number}")

    def clone_shallow(self):
        """A depth-1 clone of the fixture, the way a pipeline checks out."""
        clone = os.path.join(self.workspace.name, "shallow")
        subprocess.run(["git", "clone", "-q", "--depth", "1",
                        f"file://{self.repository}", clone], check=True)
        return clone, os.path.join(clone, "docs")

    def paths_of(self, root):
        found = []
        for directory, _, file_names in os.walk(root):
            if ".git" in directory.split(os.sep):
                continue
            for file_name in file_names:
                absolute = os.path.join(directory, file_name)
                found.append(os.path.relpath(absolute, root).replace(os.sep, "/"))
        return sorted(found)


class CommitDateTest(DocumentationSetFixture):
    """Whether the image was exported after the diagram was last edited."""

    def test_a_diagram_committed_together_with_its_export_is_accepted(self):
        report = check_diagram_sources(self.root, self.paths())

        self.assertTrue(report.accepted)
        self.assertEqual(1, report.pairs_checked)
        self.assertEqual(0, report.pairs_uncommitted)

    def test_a_source_committed_after_its_image_is_reported(self):
        self.edit_the_source_only()

        report = check_diagram_sources(self.root, self.paths())

        self.assertFalse(report.accepted)
        self.assertEqual(1, len(report.findings))
        finding = report.findings[0]
        self.assertEqual(DiagramFindingCode.STALE_DIAGRAM_IMAGE, finding.code)
        self.assertEqual("images/overview.drawio", finding.path)
        self.assertIn("images/overview.svg", finding.message)
        self.assertIn("export it over the image next to it", finding.message)

    def test_a_source_and_an_image_committed_in_the_same_second_are_told_apart(self):
        # Two commits can share a committer date, so the dates alone cannot decide and
        # the history has to: without the ancestry tiebreak this case passes and the check is blind
        # to anything committed within a second of the export.
        image = self.git("log", "-1", "--format=%ct", "--", "docs/images/overview.svg")
        # Reuse the image's date explicitly, even if creating the next commit takes a second.
        with patch.dict(os.environ, {"GIT_COMMITTER_DATE": f"@{image.stdout.strip()} +0000"}):
            self.edit_the_source_only()
        source = self.git("log", "-1", "--format=%ct", "--", "docs/images/overview.drawio")
        self.assertEqual(source.stdout.strip(), image.stdout.strip(),
                         "the fixture is meant to produce two commits in one second")

        report = check_diagram_sources(self.root, self.paths())

        self.assertFalse(report.accepted)
        self.assertEqual(DiagramFindingCode.STALE_DIAGRAM_IMAGE, report.findings[0].code)

    def test_re_exporting_the_image_accepts_the_diagram_again(self):
        self.edit_the_source_only()
        self.write("images/overview.svg", "<svg>v2</svg>\n")
        self.commit("exported the reworked diagram")

        self.assertTrue(check_diagram_sources(self.root, self.paths()).accepted)

    def test_an_image_newer_than_its_source_is_accepted(self):
        self.write("images/overview.svg", "<svg>v1 tidied</svg>\n")
        self.commit("re-exported with the current draw.io")

        self.assertTrue(check_diagram_sources(self.root, self.paths()).accepted)

    def test_a_set_without_a_diagram_costs_no_git_call(self):
        os.remove(os.path.join(self.root, "images/overview.drawio"))

        report = check_diagram_sources(self.root, self.paths())

        self.assertTrue(report.accepted)
        self.assertEqual(0, report.pairs_checked)
        self.assertEqual([], report.findings)

    def test_an_uncommitted_pair_is_counted_and_skipped(self):
        # A diagram being added right now has nothing to compare against, and refusing it would
        # make the check impossible to run on a working tree.
        self.write("images/new.drawio", "<mxfile/>\n")
        self.write("images/new.svg", "<svg/>\n")

        report = check_diagram_sources(self.root, self.paths())

        self.assertTrue(report.accepted)
        self.assertEqual(2, report.pairs_checked)
        self.assertEqual(1, report.pairs_uncommitted)

    def test_a_diagram_outside_a_git_checkout_is_reported_as_undatable(self):
        with TemporaryDirectory() as plain:
            os.makedirs(os.path.join(plain, "images"))
            for name in ("images/overview.drawio", "images/overview.svg"):
                with open(os.path.join(plain, name), "w", encoding="utf-8") as handle:
                    handle.write("x")

            report = check_diagram_sources(plain, ["images/overview.drawio",
                                                   "images/overview.svg"])

        self.assertFalse(report.accepted)
        self.assertEqual(DiagramFindingCode.UNDATABLE_DIAGRAM_HISTORY, report.findings[0].code)
        self.assertIsNone(report.findings[0].path, "it is about the set, not about one file")


class ShallowCheckoutTest(DocumentationSetFixture):
    """A shallow checkout answers with its boundary commit, which is not a date."""

    def test_a_shallow_checkout_is_reported_as_undatable_rather_than_accepted(self):
        self.edit_the_source_only()
        self.add_history(3)
        _, root = self.clone_shallow()

        report = check_diagram_sources(root, self.paths_of(root))

        # With no history every file dates to the boundary commit, so the stale diagram would look
        # exactly as old as its image and sail through.
        self.assertFalse(report.accepted)
        self.assertEqual(DiagramFindingCode.UNDATABLE_DIAGRAM_HISTORY, report.findings[0].code)
        self.assertIn("does not reach back", report.findings[0].message)

    def test_deepening_fetches_enough_history_to_catch_a_stale_diagram(self):
        self.edit_the_source_only()
        self.add_history(3)
        _, root = self.clone_shallow()

        report = check_diagram_sources(root, self.paths_of(root), deepen=True)

        self.assertFalse(report.accepted)
        self.assertEqual(DiagramFindingCode.STALE_DIAGRAM_IMAGE, report.findings[0].code)

    def test_deepening_accepts_a_shallow_checkout_whose_diagram_is_up_to_date(self):
        self.add_history(3)
        _, root = self.clone_shallow()

        report = check_diagram_sources(root, self.paths_of(root), deepen=True)

        self.assertTrue(report.accepted)
        self.assertEqual(1, report.pairs_checked)

    def test_a_set_without_a_diagram_is_never_deepened(self):
        os.remove(os.path.join(self.root, "images/overview.drawio"))
        self.commit("dropped the diagram")
        self.add_history(3)
        clone, root = self.clone_shallow()

        report = check_diagram_sources(root, self.paths_of(root), deepen=True)

        self.assertTrue(report.accepted)
        # The economics of the whole thing: the jEAP doc workflow checks out at depth 1, and a
        # repository that documents without a diagram must not pay for history to find that out.
        shallow = subprocess.run(["git", "-C", clone, "rev-parse", "--is-shallow-repository"],
                                 capture_output=True, text=True, check=True)
        self.assertEqual("true", shallow.stdout.strip())


if __name__ == "__main__":
    unittest.main()
