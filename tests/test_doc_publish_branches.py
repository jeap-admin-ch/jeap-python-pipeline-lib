import unittest

from jeap_pipeline.doc_publish_branches import (RULE_DEFAULT_BRANCH, RULE_PUBLISH_BRANCHES,
                                                RULE_TAG, branch_matches, publish_branches_of,
                                                publishes_from)
from jeap_pipeline.doc_service_operations import DocumentationConfigError

CONFIGURATION = {
    "system": "orders",
    "docs": [{"path": "./docs", "type": "system-docs", "template": "arc42",
              "source-format": "markdown"}],
}


def _with(patterns):
    return dict(CONFIGURATION, **{"publish-branches": patterns})


class PublishBranchesOfTest(unittest.TestCase):

    def test_a_repository_that_states_none_has_none(self):
        self.assertIsNone(publish_branches_of(CONFIGURATION))

    def test_the_patterns_are_read_in_the_order_they_are_written(self):
        self.assertEqual(["master", "feature/E2E-Test-*"],
                         publish_branches_of(_with(["master", "feature/E2E-Test-*"])))

    def test_an_empty_list_is_a_configuration_error(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            publish_branches_of(_with([]))

        self.assertIn("publish-branches", str(refused.exception))
        self.assertIn("empty", str(refused.exception))

    def test_something_that_is_not_a_list_is_refused(self):
        with self.assertRaises(DocumentationConfigError):
            publish_branches_of(_with("master"))

    def test_an_entry_that_is_not_a_branch_pattern_is_refused(self):
        for patterns in ([""], ["   "], [42], [None], [["master"]]):
            with self.subTest(patterns=patterns):
                with self.assertRaises(DocumentationConfigError):
                    publish_branches_of(_with(patterns))

    def test_the_source_is_named_in_the_message(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            publish_branches_of(_with([]), "./.github/jeapDocsPipelineConfig.json")

        self.assertIn("./.github/jeapDocsPipelineConfig.json", str(refused.exception))


class BranchMatchesTest(unittest.TestCase):

    def test_a_name_matches_itself_and_nothing_else(self):
        self.assertTrue(branch_matches("master", "master"))
        self.assertFalse(branch_matches("master-2", "master"))
        self.assertFalse(branch_matches("release/master", "master"))

    def test_a_star_does_not_cross_a_slash(self):
        self.assertTrue(branch_matches("release/1.2", "release/*"))
        self.assertFalse(branch_matches("release/1.2/hotfix", "release/*"))

    def test_two_stars_cross_a_slash(self):
        self.assertTrue(branch_matches("feature/a", "feature/**"))
        self.assertTrue(branch_matches("feature/a/b/c", "feature/**"))

    def test_a_question_mark_is_one_character_that_is_not_a_slash(self):
        self.assertTrue(branch_matches("master", "maste?"))
        self.assertFalse(branch_matches("mast", "maste?"))
        self.assertFalse(branch_matches("a/b", "a?b"))

    def test_a_star_matches_an_empty_rest(self):
        self.assertTrue(branch_matches("release/", "release/*"))

    def test_what_is_special_in_a_regular_expression_is_not_special_here(self):
        self.assertTrue(branch_matches("release/1.2", "release/1.2"))
        self.assertFalse(branch_matches("release/1x2", "release/1.2"))
        self.assertTrue(branch_matches("feature/a+b", "feature/a+b"))

    def test_the_pattern_matches_the_whole_name(self):
        self.assertFalse(branch_matches("feature/master", "master"))
        self.assertFalse(branch_matches("masterly", "master"))

    def test_the_branches_the_end_to_end_tests_create(self):
        pattern = "feature/E2E-Test-*"
        self.assertTrue(branch_matches("feature/E2E-Test-9a1c2f8-for-master-abc123", pattern))
        self.assertFalse(branch_matches("feature/something-else", pattern))
        self.assertFalse(branch_matches("feature/E2E-Test-9a1/deeper", pattern))


class PublishesFromTest(unittest.TestCase):

    def test_without_patterns_the_default_branch_publishes(self):
        decision = publishes_from("master", None, "master")

        self.assertTrue(decision.publishes)
        self.assertTrue(decision)
        self.assertEqual(RULE_DEFAULT_BRANCH, decision.rule)
        self.assertEqual("master", decision.branch)
        self.assertIn("default branch", decision.reason)

    def test_without_patterns_every_other_branch_publishes_nothing(self):
        decision = publishes_from("feature/a-change", None, "master")

        self.assertFalse(decision.publishes)
        self.assertFalse(decision)
        self.assertEqual(RULE_DEFAULT_BRANCH, decision.rule)
        self.assertIn("feature/a-change", decision.reason)
        self.assertIn("publish-branches", decision.reason)

    def test_a_full_ref_is_taken_as_the_branch_it_names(self):
        self.assertTrue(publishes_from("refs/heads/master", None, "master").publishes)
        self.assertEqual("master", publishes_from("refs/heads/master", None, "master").branch)

    def test_patterns_replace_the_default_branch_rule(self):
        decision = publishes_from("master", ["release/*"], "master")

        self.assertFalse(decision.publishes)
        self.assertEqual(RULE_PUBLISH_BRANCHES, decision.rule)
        self.assertIn("'release/*'", decision.reason)

    def test_a_branch_a_pattern_matches_publishes(self):
        decision = publishes_from("feature/E2E-Test-9a1", ["master", "feature/E2E-Test-*"],
                                  "master")

        self.assertTrue(decision.publishes)
        self.assertEqual(RULE_PUBLISH_BRANCHES, decision.rule)
        self.assertEqual("feature/E2E-Test-*", decision.pattern)
        self.assertIn("feature/E2E-Test-*", decision.reason)

    def test_a_branch_no_pattern_matches_publishes_nothing(self):
        decision = publishes_from("feature/a-change", ["master", "release/*"], "master")

        self.assertFalse(decision.publishes)
        self.assertIsNone(decision.pattern)
        self.assertIn("'master'", decision.reason)
        self.assertIn("'release/*'", decision.reason)

    def test_the_patterns_decide_without_a_default_branch(self):
        self.assertTrue(publishes_from("docs", ["docs"]).publishes)

    def test_a_tag_publishes_nothing(self):
        decision = publishes_from("refs/tags/v1.4.0", ["master", "**"], "master")

        self.assertFalse(decision.publishes)
        self.assertEqual(RULE_TAG, decision.rule)
        self.assertIsNone(decision.branch)
        self.assertIn("v1.4.0", decision.reason)

    def test_an_empty_list_of_patterns_is_refused(self):
        with self.assertRaises(DocumentationConfigError):
            publishes_from("master", [], "master")

    def test_no_ref_is_refused(self):
        with self.assertRaises(ValueError):
            publishes_from("", None, "master")

    def test_nothing_to_decide_with_is_refused(self):
        with self.assertRaises(ValueError) as refused:
            publishes_from("master", None, None)

        self.assertIn("default branch", str(refused.exception))

    def test_the_configuration_and_the_decision_work_together(self):
        configuration = _with(["master", "feature/E2E-Test-*"])

        patterns = publish_branches_of(configuration)

        self.assertTrue(publishes_from("refs/heads/feature/E2E-Test-1", patterns, "master"))
        self.assertTrue(publishes_from("refs/heads/master", patterns, "master"))
        self.assertFalse(publishes_from("refs/heads/feature/other", patterns, "master"))


if __name__ == "__main__":
    unittest.main()
