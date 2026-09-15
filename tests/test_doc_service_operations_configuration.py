import unittest

from jeap_pipeline.doc_service_operations import (DocumentationConfigError, DocumentationSet,
                                                  documentation_sets_from_config,
                                                  documentation_sets_from_entries)

MARKDOWN_SET = {
    "path": "./docs",
    "type": "component-docs",
    "template": "arc42",
    "source-format": "markdown",
}

HTML_SET = {
    "path": "./html-docs/configuration-reference",
    "type": "component-docs",
    "template": "arc42",
    "source-format": "html",
    "location": "8-crosscutting-concepts",
    "topic": "configuration-reference",
    "label": "Configuration Reference",
}

SYSTEM = {"system": "orders", "docs": [dict(MARKDOWN_SET, type="system-docs")]}
COMPONENT = {"system": "orders", "component": "foo-bar-scs", "docs": [MARKDOWN_SET]}
LIBRARY = {"system": "orders", "library": "orders-common-lib",
           "docs": [dict(MARKDOWN_SET, type="library-docs")]}

PROVENANCE = {
    "source-repository": "https://github.com/example-org/foo-bar-example",
    "source-revision": "9a1c2f8e5b4d3c2a1908f7e6d5c4b3a291807f6e",
    "source-ref": "develop",
    "source-timestamp": "2026-09-11T07:12:00+02:00",
    "build-url": "https://github.com/example-org/foo-bar-example/actions/runs/1234567890",
    "generated-at": "2026-09-11T07:15:00+02:00",
}


def _component(*sets, **root):
    """A component configuration carrying the given documentation sets."""
    return dict({"system": "orders", "component": "foo-bar-scs", "docs": list(sets)},
                **root)


class DocumentationSetsFromConfigTest(unittest.TestCase):

    def test_reads_the_documented_example(self):
        sets = documentation_sets_from_config(_component(MARKDOWN_SET, HTML_SET), "the example")

        self.assertEqual(2, len(sets))
        self.assertEqual("./docs", sets[0].path)
        self.assertEqual("markdown", sets[0].source_format)
        self.assertEqual("Configuration Reference", sets[1].label)
        self.assertEqual("configuration-reference", sets[1].topic)

    def test_what_the_repository_documents_holds_for_every_set(self):
        sets = documentation_sets_from_config(_component(MARKDOWN_SET, HTML_SET))

        for documentation_set in sets:
            self.assertEqual("orders", documentation_set.system)
            self.assertEqual("foo-bar-scs", documentation_set.component)

    def test_a_library_set_names_a_library(self):
        self.assertEqual("orders-common-lib",
                         documentation_sets_from_config(LIBRARY)[0].library)

    def test_the_subject_is_the_component_the_library_or_the_system(self):
        self.assertEqual("orders", documentation_sets_from_config(SYSTEM)[0].subject)
        self.assertEqual("foo-bar-scs",
                         documentation_sets_from_config(COMPONENT)[0].subject)
        self.assertEqual("orders-common-lib",
                         documentation_sets_from_config(LIBRARY)[0].subject)

    def test_version_and_site_are_part_of_the_contract_and_belong_to_the_repository(self):
        sets = documentation_sets_from_config(
            _component(MARKDOWN_SET, HTML_SET, version="1.4.0", site="governance"))

        for documentation_set in sets:
            self.assertEqual("1.4.0", documentation_set.version)
            self.assertEqual("governance", documentation_set.site)

    def test_the_set_describes_itself_for_a_report(self):
        self.assertEqual("./docs (component-docs, foo-bar-scs, arc42, markdown)",
                         documentation_sets_from_config(COMPONENT)[0].describe())


class RootTest(unittest.TestCase):

    def test_a_configuration_that_is_not_an_object_is_rejected(self):
        for configuration in ([MARKDOWN_SET], "./docs", 42, None):
            with self.assertRaises(DocumentationConfigError) as raised:
                documentation_sets_from_config(configuration, "the file")
            self.assertIn("has to hold an object", str(raised.exception))

    def test_a_configuration_that_is_still_a_list_says_what_is_expected_instead(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config([MARKDOWN_SET], "the file")

        message = str(raised.exception)
        self.assertIn("not a list", message)
        self.assertIn("'docs'", message)

    def test_an_unknown_root_key_is_rejected_naming_the_allowed_ones(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config(_component(MARKDOWN_SET, systen="orders"), "the file")

        message = str(raised.exception)
        self.assertIn("'systen'", message)
        self.assertIn("at the root", message)
        self.assertIn("component, docs, library, publish-branches, site, system, version", message)

    def test_a_set_key_at_the_root_is_rejected_and_told_where_it_belongs(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config(_component(MARKDOWN_SET, path="./docs"), "the file")

        message = str(raised.exception)
        self.assertIn("'path'", message)
        self.assertIn("belongs to an entry of 'docs'", message)

    def test_a_configuration_without_docs_is_rejected(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config({"system": "orders"}, "the file")
        self.assertIn("names no 'docs'", str(raised.exception))

    def test_docs_that_is_not_a_list_is_rejected(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config({"system": "orders", "docs": MARKDOWN_SET}, "the file")
        self.assertIn("has to hold a list", str(raised.exception))

    def test_an_empty_docs_is_rejected(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config({"system": "orders", "docs": []}, "the file")
        self.assertIn("is empty", str(raised.exception))

    def test_a_set_that_is_not_an_object_is_rejected(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config({"system": "orders", "docs": ["./docs"]}, "the file")
        self.assertIn("has to be an object", str(raised.exception))


class ValueTypeTest(unittest.TestCase):
    """Every value of a documentation configuration is a JSON string."""

    def test_a_number_is_rejected_naming_the_key_and_the_type(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config({"system": 42, "docs": [dict(MARKDOWN_SET,
                                                                       type="system-docs")]},
                                           "jeapDocsPipelineConfig.json")

        message = str(raised.exception)
        self.assertIn("'system' is a int, not a string", message)
        self.assertIn("JSON string", message)

    def test_a_number_is_not_read_as_a_slug(self):
        # str(42) matches the slug pattern, so a slug check on its own would let it through and the
        # doc service would answer about a system nobody named.
        with self.assertRaises(DocumentationConfigError):
            DocumentationSet(path="./docs", type="system-docs", system=42, template="arc42",
                             source_format="markdown")

    def test_a_list_where_a_string_belongs_is_rejected_rather_than_raising(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config(
                {"system": "orders", "docs": [dict(MARKDOWN_SET, type=["system-docs"])]})

        self.assertIn("'type' is a list, not a string", str(raised.exception))

    def test_every_key_that_takes_a_string_is_checked(self):
        for key in ("path", "type", "system", "template", "source_format", "component", "library",
                    "location", "topic", "label", "version", "site"):
            values = dict(path="./docs", type="component-docs", system="orders", template="arc42",
                          source_format="markdown", component="a-component")
            values[key] = 1
            with self.assertRaises(DocumentationConfigError, msg=key) as raised:
                DocumentationSet(**values)
            self.assertIn(f"'{key.replace('_', '-')}' is a int, not a string",
                          str(raised.exception))


class DocumentationSetTest(unittest.TestCase):

    def test_an_unknown_key_is_rejected_naming_it_and_the_set(self):
        entry = dict(MARKDOWN_SET)
        entry["source-fomat"] = "markdown"

        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config(_component(MARKDOWN_SET, entry),
                                           "jeapDocsPipelineConfig.json")

        message = str(raised.exception)
        self.assertIn("jeapDocsPipelineConfig.json, docs[1]", message)
        self.assertIn("'source-fomat'", message)
        self.assertIn("source-format", message, "the message names the keys that do exist")

    def test_a_subject_key_in_a_set_is_rejected_and_told_where_it_belongs(self):
        for key, value in (("system", "orders"), ("component", "a-component"),
                           ("library", "a-lib"), ("version", "1.0.0"), ("site", "a-site")):
            entry = dict(MARKDOWN_SET)
            entry[key] = value
            with self.assertRaises(DocumentationConfigError) as raised:
                documentation_sets_from_config(_component(entry), "the file")
            message = str(raised.exception)
            self.assertIn(f"'{key}' belongs at the root", message)
            self.assertIn("said once", message)

    def test_a_missing_required_key_is_rejected(self):
        for missing in ("path", "type", "template", "source-format"):
            entry = dict(MARKDOWN_SET)
            del entry[missing]
            with self.assertRaises(DocumentationConfigError) as raised:
                documentation_sets_from_config(_component(entry))
            self.assertIn(f"'{missing}' is required", str(raised.exception))

    def test_a_missing_system_is_rejected(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config({"component": "a-component", "docs": [MARKDOWN_SET]})
        self.assertIn("'system' is required", str(raised.exception))

    def test_an_unknown_type_is_rejected(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config(_component(dict(MARKDOWN_SET, type="module-docs")))
        self.assertIn("component-docs", str(raised.exception))

    def test_an_unknown_source_format_is_rejected(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config(
                _component(dict(MARKDOWN_SET, **{"source-format": "asciidoc"})))
        self.assertIn("markdown", str(raised.exception))

    def test_a_component_is_required_for_component_docs(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config({"system": "orders", "docs": [MARKDOWN_SET]})
        self.assertIn("'component' is required for type 'component-docs'", str(raised.exception))

    def test_a_component_does_not_belong_to_system_docs(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config(_component(dict(MARKDOWN_SET, type="system-docs")))
        self.assertIn("does not belong to type 'system-docs'", str(raised.exception))

    def test_a_library_does_not_belong_to_component_docs(self):
        # A configuration cannot express this - a root naming both is refused above - so the rule
        # itself is checked on the set.
        with self.assertRaises(DocumentationConfigError) as raised:
            DocumentationSet(path="./docs", type="component-docs", system="orders",
                             component="a-component", library="a-lib", template="arc42",
                             source_format="markdown")
        self.assertIn("'library' does not belong to type 'component-docs'", str(raised.exception))

    def test_a_root_naming_a_component_and_a_library_is_refused_at_the_root(self):
        # Every set inherits what the root says, so a repository documents one of the two. Refusing
        # it here beats the confusing per-set message it would otherwise produce.
        configuration = {"system": "orders", "component": "a-component", "library": "a-lib",
                         "docs": [MARKDOWN_SET]}

        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config(configuration, "the file")

        message = str(raised.exception)
        self.assertIn("both a 'component' and a 'library'", message)
        self.assertIn("documents one of the two", message)

    def test_location_topic_and_label_are_required_for_html(self):
        for missing in ("location", "topic", "label"):
            entry = dict(HTML_SET)
            del entry[missing]
            with self.assertRaises(DocumentationConfigError) as raised:
                documentation_sets_from_config(_component(entry))
            self.assertIn(f"'{missing}' is required for source-format 'html'",
                          str(raised.exception))

    def test_location_topic_and_label_are_refused_for_markdown(self):
        for key, value in (("location", "6-runtime-view"), ("topic", "a-topic"),
                           ("label", "A Label")):
            entry = dict(MARKDOWN_SET)
            entry[key] = value
            with self.assertRaises(DocumentationConfigError) as raised:
                documentation_sets_from_config(_component(entry))
            self.assertIn(f"'{key}' belongs to source-format 'html' only", str(raised.exception))

    def test_a_value_that_is_not_a_slug_is_rejected(self):
        with self.assertRaises(DocumentationConfigError) as raised:
            documentation_sets_from_config(_component(MARKDOWN_SET, system="JME"))
        self.assertIn("is not a slug", str(raised.exception))

        for key, value in (("template", "arc 42"), ("topic", "Configuration-Reference")):
            entry = dict(HTML_SET)
            entry[key] = value
            with self.assertRaises(DocumentationConfigError) as raised:
                documentation_sets_from_config(_component(entry))
            self.assertIn("is not a slug", str(raised.exception))

    def test_a_path_leaving_the_repository_is_rejected(self):
        for path in ("/etc/passwd", "../../etc", "docs/../../out"):
            with self.assertRaises(DocumentationConfigError) as raised:
                documentation_sets_from_config(_component(dict(MARKDOWN_SET, path=path)))
            self.assertIn("'path'", str(raised.exception))

    def test_a_path_walking_up_inside_the_repository_is_accepted(self):
        documentation_sets_from_config(_component(dict(MARKDOWN_SET, path="target/../docs")))

    def test_a_set_built_directly_is_validated_too(self):
        with self.assertRaises(DocumentationConfigError):
            DocumentationSet(path="./docs", type="system-docs", system="orders", template="arc42",
                             source_format="mdx")


class ValidationQueryParametersTest(unittest.TestCase):

    def test_system_docs_send_the_four_parameters_the_structure_depends_on(self):
        parameters = documentation_sets_from_config(SYSTEM)[0].validation_query_parameters()

        self.assertEqual({"type": "system-docs", "system": "orders", "template": "arc42",
                          "source-format": "markdown"}, parameters)

    def test_component_docs_add_the_component(self):
        parameters = documentation_sets_from_config(COMPONENT)[0].validation_query_parameters()

        self.assertEqual({"type": "component-docs", "system": "orders",
                          "component": "foo-bar-scs", "template": "arc42",
                          "source-format": "markdown"}, parameters)

    def test_library_docs_add_the_library(self):
        parameters = documentation_sets_from_config(LIBRARY)[0].validation_query_parameters()

        self.assertEqual("orders-common-lib", parameters["library"])
        self.assertNotIn("component", parameters)

    def test_an_html_set_adds_the_location_and_the_topic_but_not_the_label(self):
        parameters = documentation_sets_from_config(
            _component(HTML_SET))[0].validation_query_parameters()

        self.assertEqual({"type": "component-docs", "system": "orders",
                          "component": "foo-bar-scs", "template": "arc42",
                          "source-format": "html", "location": "8-crosscutting-concepts",
                          "topic": "configuration-reference"}, parameters)

    def test_what_the_endpoint_refuses_is_never_sent(self):
        parameters = documentation_sets_from_config(
            _component(MARKDOWN_SET, version="1.4.0",
                       site="governance"))[0].validation_query_parameters()

        for refused in ("version", "site", "label", "source-repository", "source-revision",
                        "source-ref", "source-timestamp", "build-url", "generated-at", "path"):
            self.assertNotIn(refused, parameters)


class PublishBranchesKeyTest(unittest.TestCase):

    def test_the_key_is_allowed_at_the_root_and_is_not_a_documentation_set_key(self):
        sets = documentation_sets_from_config(dict(SYSTEM, **{"publish-branches": ["master"]}))

        self.assertEqual(1, len(sets))
        self.assertNotIn("publish-branches", sets[0].validation_query_parameters())
        self.assertNotIn("publish-branches",
                         sets[0].upload_query_parameters(PROVENANCE))

    def test_it_belongs_at_the_root_and_not_to_a_set(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            documentation_sets_from_config(
                _component(dict(MARKDOWN_SET, **{"publish-branches": ["master"]})))

        self.assertIn("publish-branches", str(refused.exception))


class UploadQueryParametersTest(unittest.TestCase):

    def test_system_docs_send_what_the_structure_needs_and_the_provenance(self):
        parameters = documentation_sets_from_config(SYSTEM)[0].upload_query_parameters(PROVENANCE)

        self.assertEqual(dict({"type": "system-docs", "system": "orders", "template": "arc42",
                               "source-format": "markdown"}, **PROVENANCE), parameters)

    def test_component_docs_carry_the_version_of_the_component(self):
        parameters = documentation_sets_from_config(COMPONENT)[0].upload_query_parameters(
            PROVENANCE, "1.0.0-20260911073000")

        self.assertEqual("1.0.0-20260911073000", parameters["version"])
        self.assertEqual("foo-bar-scs", parameters["component"])

    def test_library_docs_carry_the_version_of_the_library(self):
        parameters = documentation_sets_from_config(LIBRARY)[0].upload_query_parameters(
            PROVENANCE, "1.0.0")

        self.assertEqual("1.0.0", parameters["version"])
        self.assertEqual("orders-common-lib", parameters["library"])

    def test_the_configured_version_is_sent_when_the_pipeline_resolved_none(self):
        parameters = documentation_sets_from_config(
            _component(MARKDOWN_SET, version="1.4.0"))[0].upload_query_parameters(PROVENANCE)

        self.assertEqual("1.4.0", parameters["version"])

    def test_a_component_without_a_version_is_refused_before_the_doc_service_sees_it(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            documentation_sets_from_config(COMPONENT)[0].upload_query_parameters(PROVENANCE)

        self.assertIn("version", str(refused.exception))

    def test_a_system_with_a_version_is_refused_too(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            documentation_sets_from_config(SYSTEM)[0].upload_query_parameters(PROVENANCE, "1.0.0")

        self.assertIn("system documents itself", str(refused.exception))

    def test_an_html_set_adds_its_placement_and_its_label(self):
        parameters = documentation_sets_from_config(
            _component(HTML_SET))[0].upload_query_parameters(PROVENANCE, "1.0.0")

        self.assertEqual("8-crosscutting-concepts", parameters["location"])
        self.assertEqual("configuration-reference", parameters["topic"])
        self.assertEqual("Configuration Reference", parameters["label"])

    def test_the_site_is_sent_when_the_repository_names_one(self):
        parameters = documentation_sets_from_config(
            _component(MARKDOWN_SET, site="governance"))[0].upload_query_parameters(PROVENANCE,
                                                                                    "1.0.0")

        self.assertEqual("governance", parameters["site"])

    def test_the_folder_of_the_set_is_never_sent(self):
        parameters = documentation_sets_from_config(COMPONENT)[0].upload_query_parameters(
            PROVENANCE, "1.0.0")

        self.assertNotIn("path", parameters)


GENERATED_ENTRY = {
    "path": "./target/reports/apidocs",
    "type": "component-docs",
    "system": "orders",
    "component": "foo-bar-scs",
    "template": "arc42",
    "source-format": "html",
    "location": "5-building-block-view",
    "topic": "javadoc",
    "label": "Javadoc",
}


def _generated(*entries, source_formats=frozenset({"html"})):
    """Read entries of generated documentation the way a build pipeline reads them."""
    return documentation_sets_from_entries(list(entries), "the build configuration",
                                           "generated-docs", source_formats)


class DocumentationSetsFromEntriesTest(unittest.TestCase):
    """The documentation a build generates: a list, and every entry names what it is about."""

    def test_an_entry_names_its_own_subject(self):
        component, library = _generated(
            GENERATED_ENTRY,
            dict(GENERATED_ENTRY, type="library-docs", library="orders-common-lib",
                 component=None, topic="library-javadoc"))

        self.assertEqual("foo-bar-scs", component.component)
        self.assertEqual("orders", component.system)
        self.assertEqual("orders-common-lib", library.library)

    def test_a_system_report_needs_no_subject_beside_the_system(self):
        report, = _generated(dict(GENERATED_ENTRY, type="system-docs", component=None,
                                  location="10-quality-requirements", topic="system-test-report"))

        self.assertEqual("orders", report.subject)

    def test_the_entries_keep_the_order_they_are_configured_in(self):
        first, second = _generated(GENERATED_ENTRY, dict(GENERATED_ENTRY, topic="rest-docs"))

        self.assertEqual("javadoc", first.topic)
        self.assertEqual("rest-docs", second.topic)

    def test_a_version_belongs_to_the_pipeline_that_built_it(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            _generated(dict(GENERATED_ENTRY, version="1.0.0"))

        self.assertIn("'version' is not stated here", str(refused.exception))

    def test_a_site_and_the_branches_are_not_an_entry_of_the_list(self):
        for key, value in (("site", "governance"), ("publish-branches", ["master"])):
            with self.subTest(key=key):
                with self.assertRaises(DocumentationConfigError) as refused:
                    _generated(dict(GENERATED_ENTRY, **{key: value}))

                self.assertIn(f"'{key}' is not stated here", str(refused.exception))

    def test_an_unknown_key_is_refused_with_the_allowed_ones(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            _generated(dict(GENERATED_ENTRY, topci="javadoc"))

        self.assertIn("'topci'", str(refused.exception))
        self.assertIn("topic", str(refused.exception))

    def test_a_format_the_pipeline_does_not_upload_is_refused(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            _generated({"path": "./target/generated-docs", "type": "system-docs",
                        "system": "orders", "template": "arc42", "source-format": "markdown"})

        self.assertIn("this pipeline uploads html", str(refused.exception))
        self.assertIn("documentation configuration", str(refused.exception))

    def test_every_format_is_read_when_the_caller_allows_every_format(self):
        markdown, = documentation_sets_from_entries(
            [{"path": "./target/generated-docs", "type": "system-docs", "system": "orders",
              "template": "arc42", "source-format": "markdown"}], "the build configuration")

        self.assertEqual("markdown", markdown.source_format)

    def test_two_entries_of_one_place_are_refused(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            _generated(GENERATED_ENTRY, dict(GENERATED_ENTRY, path="./target/site/apidocs"))

        self.assertIn("[0] and [1]", str(refused.exception))
        self.assertIn("javadoc", str(refused.exception))

    def test_one_folder_may_be_published_under_two_topics(self):
        first, second = _generated(GENERATED_ENTRY, dict(GENERATED_ENTRY, topic="rest-docs"))

        self.assertEqual(first.path, second.path)

    def test_a_message_names_the_index_of_the_entry_it_is_about(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            _generated(GENERATED_ENTRY, dict(GENERATED_ENTRY, topic="Not A Slug"))

        self.assertIn("generated-docs[1]", str(refused.exception))

    def test_a_list_that_is_no_list_is_refused(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            documentation_sets_from_entries(GENERATED_ENTRY, "the build configuration")

        self.assertIn("has to hold a list", str(refused.exception))

    def test_an_empty_list_is_refused(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            _generated()

        self.assertIn("is empty", str(refused.exception))

    def test_an_entry_that_is_no_object_is_refused(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            _generated("./target/reports/apidocs")

        self.assertIn("has to be an object", str(refused.exception))

    def test_a_required_key_is_still_required(self):
        with self.assertRaises(DocumentationConfigError) as refused:
            _generated({key: value for key, value in GENERATED_ENTRY.items() if key != "template"})

        self.assertIn("template", str(refused.exception))


class GeneratedVersionMessageTest(unittest.TestCase):
    """A build says where its version comes from, and the refusal says so too."""

    def test_the_caller_says_where_the_version_comes_from(self):
        generated, = _generated(GENERATED_ENTRY)

        with self.assertRaises(DocumentationConfigError) as refused:
            generated.upload_query_parameters(
                PROVENANCE, version_source="Set the 'version' input of the workflow step.")

        self.assertIn("Set the 'version' input of the workflow step.", str(refused.exception))
        self.assertNotIn("documentation configuration", str(refused.exception))

    def test_without_one_the_documentation_configuration_is_named(self):
        generated, = _generated(GENERATED_ENTRY)

        with self.assertRaises(DocumentationConfigError) as refused:
            generated.upload_query_parameters(PROVENANCE)

        self.assertIn("documentation configuration", str(refused.exception))


if __name__ == "__main__":
    unittest.main()
