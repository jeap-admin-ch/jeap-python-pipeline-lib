import os
import unittest

from tempfile import TemporaryDirectory

from jeap_pipeline.doc_path_tree import DocumentationPathError, collect_documentation_paths


def _write(root, relative_path, content="x"):
    absolute = os.path.join(root, relative_path)
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    with open(absolute, "w") as target:
        target.write(content)
    return absolute


class CollectDocumentationPathsTest(unittest.TestCase):

    def test_returns_relative_sorted_paths(self):
        with TemporaryDirectory() as root:
            _write(root, "6-runtime-view/flow.md")
            _write(root, "1-intro/goals.md")
            _write(root, "1-intro/overview.png")

            self.assertEqual(["1-intro/goals.md", "1-intro/overview.png", "6-runtime-view/flow.md"],
                             collect_documentation_paths(root))

    def test_lists_files_only_and_drops_empty_directories(self):
        with TemporaryDirectory() as root:
            _write(root, "1-intro/goals.md")
            os.makedirs(os.path.join(root, "2-constraints"))

            self.assertEqual(["1-intro/goals.md"], collect_documentation_paths(root))

    def test_skips_the_git_directory(self):
        with TemporaryDirectory() as root:
            _write(root, "1-intro/goals.md")
            _write(root, ".git/config")
            _write(root, ".git/objects/ab/cdef")

            self.assertEqual(["1-intro/goals.md"], collect_documentation_paths(root))

    def test_skips_a_symlinked_file(self):
        with TemporaryDirectory() as root:
            _write(root, "1-intro/goals.md")
            os.symlink(os.path.join(root, "1-intro/goals.md"), os.path.join(root, "1-intro/link.md"))

            self.assertEqual(["1-intro/goals.md"], collect_documentation_paths(root))

    def test_skips_a_symlinked_directory(self):
        with TemporaryDirectory() as root:
            _write(root, "1-intro/goals.md")
            os.symlink(os.path.join(root, "1-intro"), os.path.join(root, "2-constraints"))

            self.assertEqual(["1-intro/goals.md"], collect_documentation_paths(root))

    def test_a_missing_folder_is_a_configuration_error(self):
        with TemporaryDirectory() as root:
            with self.assertRaises(DocumentationPathError) as raised:
                collect_documentation_paths(os.path.join(root, "docs"))
            self.assertIn("does not exist", str(raised.exception))

    def test_a_file_instead_of_a_folder_is_a_configuration_error(self):
        with TemporaryDirectory() as root:
            page = _write(root, "docs.md")
            with self.assertRaises(DocumentationPathError) as raised:
                collect_documentation_paths(page)
            self.assertIn("is not a folder", str(raised.exception))

    def test_an_empty_folder_is_an_empty_list(self):
        with TemporaryDirectory() as root:
            self.assertEqual([], collect_documentation_paths(root))


if __name__ == "__main__":
    unittest.main()
