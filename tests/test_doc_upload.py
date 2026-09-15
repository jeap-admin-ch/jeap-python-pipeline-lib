import json
import os
import tempfile
import unittest
import zipfile
from unittest.mock import MagicMock, patch

import requests

from jeap_pipeline.doc_path_tree import DocumentationPathError
from jeap_pipeline.doc_service_operations import (DocServiceError, DocServiceRequestError,
                                                  DocumentationConfigError, DocumentationSet)
from jeap_pipeline.doc_upload import (MAX_RETRY_AFTER_SECONDS, UploadProvenance,
                                      format_set_upload_report, upload_id_of,
                                      upload_documentation_bundle, upload_documentation_sets,
                                      write_documentation_bundle)

DOC_SERVICE_URL = "https://docs.example.ch"
TOKEN_URI = "https://auth.example.ch/oauth2/token"

SYSTEM_SET = DocumentationSet(path="./docs", type="system-docs", system="orders", template="arc42",
                              source_format="markdown")

COMPONENT_SET = DocumentationSet(path="./docs", type="component-docs", system="orders",
                                 component="foo-bar-scs", template="arc42",
                                 source_format="markdown")

LIBRARY_SET = DocumentationSet(path="./docs", type="library-docs", system="orders",
                               library="orders-common-lib", template="arc42",
                               source_format="markdown")

HTML_SET = DocumentationSet(path="./html-docs/configuration-reference", type="component-docs",
                            system="orders", component="foo-bar-scs", template="arc42",
                            source_format="html", location="8-crosscutting-concepts",
                            topic="configuration-reference", label="Configuration Reference")

PROVENANCE = UploadProvenance(
    source_repository="https://github.com/example-org/orders-docs",
    source_revision="9a1c2f8e5b4d3c2a1908f7e6d5c4b3a291807f6e",
    source_ref="master",
    source_timestamp="2026-09-11T07:12:00+02:00",
    build_url="https://github.com/example-org/orders-docs/actions/runs/1234567890",
    generated_at="2026-09-11T07:15:00+02:00")

STORED_BODY = {
    "uploadId": "8f1c9a2e-6a1a-4a5f-9a5e-2b0f9a3c1d77",
    "id": 42,
    "state": "PENDING",
    "sizeInBytes": 184320,
    "receivedAt": "2026-09-11T07:12:00.123Z",
}

STRUCTURE_INVALID_BODY = {
    "type": "https://jeap.admin.ch/problems/docs/invalid-upload",
    "title": "The upload does not describe a documentation set",
    "status": 422,
    "detail": "1 of its 17 file(s) break a rule of the structure template arc42.",
    "code": "STRUCTURE_INVALID",
    "template": "arc42",
    "pathsChecked": 17,
    "pathsIgnored": 0,
    "allowedFolders": ["1-intro"],
    "allowedExtensions": ["md"],
    "findings": [
        {"code": "UNKNOWN_CHAPTER", "path": "4-runtime-view/reactions.md",
         "message": "'4-runtime-view' is not a chapter of arc42. Did you mean '6-runtime-view'?"},
    ],
    "findingsOmitted": 0,
}


def _response(status_code, body=None, text=None, headers=None):
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    response.text = text if text is not None else json.dumps(body or {})
    if body is None and text is not None:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = body or {}
    return response


def _problem(status_code, code, detail="Refused.", headers=None):
    return _response(status_code,
                     {"type": "https://jeap.admin.ch/problems/docs/invalid-upload",
                      "title": "The upload does not describe a documentation set",
                      "status": status_code, "detail": detail, "code": code},
                     headers=headers)


class WriteDocumentationBundleTest(unittest.TestCase):

    def test_the_archive_holds_the_given_paths_under_their_set_relative_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "docs")
            os.makedirs(os.path.join(root, "1-intro"))
            os.makedirs(os.path.join(root, "12-glossary"))
            with open(os.path.join(root, "1-intro", "goals.md"), "w") as page:
                page.write("# Goals\n")
            with open(os.path.join(root, "12-glossary", "glossary.md"), "w") as page:
                page.write("# Glossary\n")
            bundle_path = os.path.join(directory, "documentation.zip")

            size = write_documentation_bundle(root, ["1-intro/goals.md",
                                                     "12-glossary/glossary.md"], bundle_path)

            with zipfile.ZipFile(bundle_path) as bundle:
                self.assertEqual(["1-intro/goals.md", "12-glossary/glossary.md"],
                                 sorted(bundle.namelist()))
                self.assertEqual(b"# Goals\n", bundle.read("1-intro/goals.md"))
            self.assertEqual(os.path.getsize(bundle_path), size)

    def test_a_file_of_the_folder_that_is_not_in_the_paths_is_not_packed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = os.path.join(directory, "docs")
            os.makedirs(root)
            for name in ("goals.md", "notes.txt"):
                with open(os.path.join(root, name), "w") as page:
                    page.write("x")
            bundle_path = os.path.join(directory, "documentation.zip")

            write_documentation_bundle(root, ["goals.md"], bundle_path)

            with zipfile.ZipFile(bundle_path) as bundle:
                self.assertEqual(["goals.md"], bundle.namelist())


class UploadIdTest(unittest.TestCase):

    def test_the_same_seed_and_set_produce_the_same_id(self):
        self.assertEqual(upload_id_of(SYSTEM_SET, "example-org/orders-docs/17/1"),
                         upload_id_of(SYSTEM_SET, "example-org/orders-docs/17/1"))

    def test_two_sets_of_one_run_get_different_ids(self):
        self.assertNotEqual(upload_id_of(SYSTEM_SET, "example-org/orders-docs/17/1"),
                            upload_id_of(HTML_SET, "example-org/orders-docs/17/1"))

    def test_the_next_attempt_of_a_run_gets_a_different_id(self):
        self.assertNotEqual(upload_id_of(SYSTEM_SET, "example-org/orders-docs/17/1"),
                            upload_id_of(SYSTEM_SET, "example-org/orders-docs/17/2"))

    def test_without_a_seed_every_id_is_new(self):
        self.assertNotEqual(upload_id_of(SYSTEM_SET), upload_id_of(SYSTEM_SET))

    def test_one_folder_uploaded_twice_gets_two_ids(self):
        """A build and the doc workflow of one run can upload one folder as two different sets."""
        markdown = DocumentationSet(path="./docs", type="component-docs", system="orders",
                                    component="foo-bar-scs", template="arc42",
                                    source_format="markdown")
        microsite = DocumentationSet(path="./docs", type="component-docs", system="orders",
                                     component="foo-bar-scs", template="arc42", source_format="html",
                                     location="6-runtime-view", topic="javadoc", label="Javadoc")

        self.assertNotEqual(upload_id_of(markdown, "example-org/orders/17/1"),
                            upload_id_of(microsite, "example-org/orders/17/1"))

    def test_two_topics_of_one_folder_get_two_ids(self):
        rest_docs = DocumentationSet(path="./target/docs", type="component-docs", system="orders",
                                     component="foo-bar-scs", template="arc42", source_format="html",
                                     location="6-runtime-view", topic="rest-docs", label="REST Docs")
        javadoc = DocumentationSet(path="./target/docs", type="component-docs", system="orders",
                                   component="foo-bar-scs", template="arc42", source_format="html",
                                   location="6-runtime-view", topic="javadoc", label="Javadoc")

        self.assertNotEqual(upload_id_of(rest_docs, "example-org/orders/17/1"),
                            upload_id_of(javadoc, "example-org/orders/17/1"))

    def test_two_subjects_of_one_folder_get_two_ids(self):
        component = DocumentationSet(path="./target/docs", type="component-docs", system="orders",
                                     component="foo-bar-scs", template="arc42",
                                     source_format="markdown")
        library = DocumentationSet(path="./target/docs", type="library-docs", system="orders",
                                   library="orders-common-lib", template="arc42",
                                   source_format="markdown")

        self.assertNotEqual(upload_id_of(component, "example-org/orders/17/1"),
                            upload_id_of(library, "example-org/orders/17/1"))


class VersionSourceTest(unittest.TestCase):
    """Where a caller expects the version from, when a set that needs one has none."""

    @patch('jeap_pipeline.doc_upload.fetch_client_credentials_token')
    def test_the_caller_names_where_the_version_comes_from(self, token):
        token.return_value = 'token'

        with self.assertRaises(DocumentationConfigError) as refused:
            upload_documentation_sets([COMPONENT_SET], DOC_SERVICE_URL, TOKEN_URI, 'client',
                                      'secret', PROVENANCE,
                                      version_source="Set the 'version' input of the step.")

        self.assertIn("Set the 'version' input of the step.", str(refused.exception))
        token.assert_not_called()


class UploadQueryParametersTest(unittest.TestCase):
    """What an upload says about itself is `DocumentationSet`'s; this is the provenance half."""

    def test_the_provenance_travels_with_every_upload(self):
        parameters = SYSTEM_SET.upload_query_parameters(PROVENANCE.query_parameters())

        for key, value in PROVENANCE.query_parameters().items():
            self.assertEqual(value, parameters[key])

    def test_a_run_without_a_build_url_sends_neither_it_nor_a_generated_at(self):
        parameters = UploadProvenance(source_repository="https://github.com/example-org/orders-docs",
                                      source_revision="9a1c2f8",
                                      source_ref="master",
                                      source_timestamp="2026-09-11T07:12:00+02:00").query_parameters()

        self.assertNotIn("build-url", parameters)
        self.assertNotIn("generated-at", parameters)


class UploadDocumentationBundleTest(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.bundle_path = os.path.join(self.directory.name, "documentation.zip")
        write_documentation_bundle(self.directory.name, [], self.bundle_path)

    def tearDown(self):
        self.directory.cleanup()

    def _upload(self, doc_service_url=DOC_SERVICE_URL, documentation_set=SYSTEM_SET,
                **keyword_arguments):
        return upload_documentation_bundle(
            doc_service_url, "a-token", documentation_set, self.bundle_path, "an-upload-id",
            documentation_set.upload_query_parameters(PROVENANCE.query_parameters()),
            backoff_seconds=0, **keyword_arguments)

    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_puts_the_bundle_with_its_parameters_and_its_length(self, put):
        put.return_value = _response(201, STORED_BODY)

        result = self._upload()

        url = put.call_args[0][0]
        keyword_arguments = put.call_args[1]
        headers = keyword_arguments["headers"]
        self.assertEqual(f"{DOC_SERVICE_URL}/api/uploads/docs/an-upload-id", url)
        self.assertEqual(SYSTEM_SET.upload_query_parameters(PROVENANCE.query_parameters()),
                         keyword_arguments["params"])
        self.assertEqual("Bearer a-token", headers["Authorization"])
        self.assertEqual("application/zip", headers["Content-Type"])
        self.assertEqual(str(os.path.getsize(self.bundle_path)), headers["Content-Length"])
        self.assertTrue(result.stored)
        self.assertEqual("PENDING", result.state)
        self.assertEqual(42, result.id)

    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_trailing_slash_on_the_url_does_not_double_the_path(self, put):
        put.return_value = _response(201, STORED_BODY)

        self._upload(doc_service_url=DOC_SERVICE_URL + "/")

        self.assertEqual(f"{DOC_SERVICE_URL}/api/uploads/docs/an-upload-id", put.call_args[0][0])

    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_an_upload_already_stored_is_an_outcome_and_not_an_error(self, put):
        put.return_value = _response(200, STORED_BODY)

        result = self._upload()

        self.assertFalse(result.stored)
        self.assertEqual(200, result.status_code)

    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_set_that_would_not_be_published_raises_with_its_findings(self, put):
        put.return_value = _response(422, STRUCTURE_INVALID_BODY)

        with self.assertRaises(DocServiceRequestError) as refused:
            self._upload()

        self.assertIn("STRUCTURE_INVALID", str(refused.exception))
        report = refused.exception.report
        self.assertFalse(report.accepted)
        self.assertEqual(1, len(report.findings))
        self.assertEqual("UNKNOWN_CHAPTER", report.findings[0].code)
        self.assertEqual(["1-intro"], report.allowed_folders)

    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_refused_request_names_its_code(self, put):
        for status_code, code in ((400, "UNKNOWN_PARAMETER"), (411, "LENGTH_REQUIRED"),
                                  (413, "SIZE_LIMIT_EXCEEDED"), (413, "TOO_MANY_PATHS"),
                                  (413, "UNPACKS_TO_TOO_MUCH"), (409, "UPLOAD_ID_CONFLICT"),
                                  (400, "INVALID_BUNDLE")):
            with self.subTest(code=code):
                put.return_value = _problem(status_code, code)

                with self.assertRaises(DocServiceRequestError) as refused:
                    self._upload()

                self.assertIn(code, str(refused.exception))
                self.assertIn(str(status_code), str(refused.exception))

    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_no_permission_names_the_role_the_client_needs(self, put):
        put.return_value = _response(403, None, text="")

        with self.assertRaises(DocServiceRequestError) as refused:
            self._upload()

        self.assertIn("orders_@uploads_#write", str(refused.exception).replace("%", ""))

    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_an_unusable_token_is_reported_as_one(self, put):
        put.return_value = _response(401, None, text="")

        with self.assertRaises(DocServiceRequestError) as refused:
            self._upload()

        self.assertIn("401", str(refused.exception))

    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_body_that_is_not_a_zip_is_reported_as_one(self, put):
        put.return_value = _response(415, None, text="")

        with self.assertRaises(DocServiceRequestError) as refused:
            self._upload()

        self.assertIn("ZIP", str(refused.exception))

    @patch("jeap_pipeline.doc_upload.time.sleep")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_an_upload_being_received_is_repeated_after_the_retry_after(self, put, sleep):
        put.side_effect = [_problem(409, "UPLOAD_IN_PROGRESS", headers={"Retry-After": "7"}),
                           _response(201, STORED_BODY)]

        result = self._upload()

        self.assertTrue(result.stored)
        self.assertEqual(2, put.call_count)
        sleep.assert_called_once_with(7)

    @patch("jeap_pipeline.doc_upload.time.sleep")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_an_upload_being_received_for_too_long_is_given_up_on(self, put, sleep):
        put.return_value = _problem(409, "UPLOAD_IN_PROGRESS")

        with self.assertRaises(DocServiceRequestError) as refused:
            self._upload(in_progress_attempts=3)

        self.assertIn("UPLOAD_IN_PROGRESS", str(refused.exception))
        self.assertEqual(3, put.call_count)

    @patch("jeap_pipeline.doc_upload.time.sleep")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_server_error_is_retried_and_then_raises(self, put, sleep):
        put.return_value = _response(503, None, text="Service Unavailable")

        with self.assertRaises(DocServiceError):
            self._upload(attempts=3)

        self.assertEqual(3, put.call_count)

    @patch("jeap_pipeline.doc_upload.time.sleep")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_connection_error_is_retried(self, put, sleep):
        put.side_effect = [requests.exceptions.ConnectionError("no route"),
                           _response(201, STORED_BODY)]

        result = self._upload()

        self.assertTrue(result.stored)
        self.assertEqual(2, put.call_count)

    @patch("jeap_pipeline.doc_upload.time.sleep")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_every_attempt_sends_the_same_file(self, put, sleep):
        sent = []

        def record(*arguments, **keyword_arguments):
            sent.append(keyword_arguments["data"].read())
            return (_response(503, None, text="")
                    if len(sent) == 1 else _response(201, STORED_BODY))

        put.side_effect = record

        self._upload()

        self.assertEqual(2, len(sent))
        self.assertEqual(sent[0], sent[1])

    @patch("jeap_pipeline.doc_upload.time.sleep")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_retry_after_nobody_can_wait_for_is_capped(self, put, sleep):
        put.side_effect = [_problem(409, "UPLOAD_IN_PROGRESS", headers={"Retry-After": "86400"}),
                           _response(201, STORED_BODY)]

        self._upload()

        sleep.assert_called_once_with(MAX_RETRY_AFTER_SECONDS)

    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_an_unreadable_refusal_says_that_an_upload_was_answered(self, put):
        put.return_value = _response(422, None, text="<html>Gateway</html>")

        with self.assertRaises(DocServiceError) as failed:
            self._upload()

        self.assertIn("answered the upload of ./docs", str(failed.exception))
        self.assertNotIn("validation", str(failed.exception))

    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_an_answer_that_is_not_json_is_reported(self, put):
        put.return_value = _response(201, None, text="<html>Gateway</html>")

        with self.assertRaises(DocServiceError) as failed:
            self._upload()

        self.assertIn("not JSON", str(failed.exception))


class UploadDocumentationSetsTest(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = os.path.join(self.directory.name, "docs")
        os.makedirs(os.path.join(root, "1-intro"))
        with open(os.path.join(root, "1-intro", "goals.md"), "w") as page:
            page.write("# Goals\n")

        microsite = os.path.join(self.directory.name, "html-docs", "configuration-reference")
        os.makedirs(microsite)
        with open(os.path.join(microsite, "index.html"), "w") as page:
            page.write("<html lang=\"en\"></html>\n")

    def tearDown(self):
        self.directory.cleanup()

    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_uploads_every_markdown_set_with_one_token(self, put, token):
        put.return_value = _response(201, STORED_BODY)

        outcome = upload_documentation_sets([SYSTEM_SET], DOC_SERVICE_URL, TOKEN_URI,
                                            "orders-doc-pipeline", "a-secret", PROVENANCE,
                                            working_directory=self.directory.name)

        self.assertTrue(outcome.accepted)
        self.assertEqual(1, outcome.uploaded_sets)
        self.assertEqual(1, outcome.sets[0].files)
        self.assertEqual(1, token.call_count)
        self.assertIn("201 Created", outcome.report)

    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_an_html_set_is_uploaded_with_where_it_is_embedded(self, put, token):
        put.return_value = _response(201, STORED_BODY)

        outcome = upload_documentation_sets([HTML_SET], DOC_SERVICE_URL, TOKEN_URI,
                                            "orders-doc-pipeline", "a-secret", PROVENANCE,
                                            versions={HTML_SET.path: "1.0.0"},
                                            working_directory=self.directory.name)

        parameters = put.call_args[1]["params"]
        self.assertTrue(outcome.accepted)
        self.assertEqual(1, outcome.uploaded_sets)
        self.assertEqual("html", parameters["source-format"])
        self.assertEqual("8-crosscutting-concepts", parameters["location"])
        self.assertEqual("configuration-reference", parameters["topic"])
        self.assertEqual("Configuration Reference", parameters["label"])

    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_markdown_set_sends_no_placement(self, put, token):
        put.return_value = _response(201, STORED_BODY)

        upload_documentation_sets([SYSTEM_SET], DOC_SERVICE_URL, TOKEN_URI, "orders-doc-pipeline",
                                  "a-secret", PROVENANCE, working_directory=self.directory.name)

        parameters = put.call_args[1]["params"]
        for placement in ("location", "topic", "label"):
            self.assertNotIn(placement, parameters)

    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_the_version_of_a_set_is_sent_with_it(self, put, token):
        put.return_value = _response(201, STORED_BODY)

        upload_documentation_sets([COMPONENT_SET], DOC_SERVICE_URL, TOKEN_URI, "orders-doc-pipeline",
                                  "a-secret", PROVENANCE,
                                  versions={"./docs": "1.0.0-20260911073000"},
                                  working_directory=self.directory.name)

        self.assertEqual("1.0.0-20260911073000", put.call_args[1]["params"]["version"])

    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_set_the_doc_service_would_not_publish_is_reported_with_its_findings(self, put, token):
        put.return_value = _response(422, STRUCTURE_INVALID_BODY)

        outcome = upload_documentation_sets([SYSTEM_SET], DOC_SERVICE_URL, TOKEN_URI,
                                            "orders-doc-pipeline", "a-secret", PROVENANCE,
                                            working_directory=self.directory.name)

        self.assertFalse(outcome.accepted)
        self.assertTrue(outcome.sets[0].refused)
        self.assertEqual(0, outcome.uploaded_sets)
        self.assertIn("UNKNOWN_CHAPTER", outcome.report)
        self.assertIn("4-runtime-view/reactions.md", outcome.report)
        self.assertIn("would not be published", outcome.report)

    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_refused_request_is_not_turned_into_a_report(self, put, token):
        put.return_value = _problem(400, "UNKNOWN_PARAMETER")

        with self.assertRaises(DocServiceRequestError):
            upload_documentation_sets([SYSTEM_SET], DOC_SERVICE_URL, TOKEN_URI, "orders-doc-pipeline",
                                      "a-secret", PROVENANCE,
                                      working_directory=self.directory.name)

    @patch("jeap_pipeline.doc_upload.time.sleep")
    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_giving_up_on_an_upload_in_progress_reports_the_refusal(self, put, token, sleep):
        put.return_value = _problem(409, "UPLOAD_IN_PROGRESS")

        with self.assertRaises(DocServiceRequestError) as refused:
            upload_documentation_sets([SYSTEM_SET], DOC_SERVICE_URL, TOKEN_URI, "orders-doc-pipeline",
                                      "a-secret", PROVENANCE,
                                      working_directory=self.directory.name)

        message = str(refused.exception)
        self.assertIn("UPLOAD_IN_PROGRESS", message)
        self.assertIn("Running the pipeline again", message)
        self.assertNotIn("  ", message)
        self.assertIsNone(refused.exception.report)

    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_set_that_cannot_say_its_version_stops_the_run_before_anything_is_uploaded(
            self, put, token):
        with self.assertRaises(DocumentationConfigError) as refused:
            upload_documentation_sets([SYSTEM_SET, COMPONENT_SET], DOC_SERVICE_URL, TOKEN_URI,
                                      "orders-doc-pipeline", "a-secret", PROVENANCE,
                                      working_directory=self.directory.name)

        self.assertIn("version", str(refused.exception))
        self.assertEqual(0, put.call_count)
        self.assertEqual(0, token.call_count)

    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_set_whose_folder_is_missing_stops_the_run_before_anything_is_uploaded(self, put, token):
        missing = DocumentationSet(path="./spec", type="system-docs", system="orders",
                                   template="arc42", source_format="markdown")

        with self.assertRaises(DocumentationPathError) as refused:
            upload_documentation_sets([SYSTEM_SET, missing], DOC_SERVICE_URL, TOKEN_URI,
                                      "orders-doc-pipeline", "a-secret", PROVENANCE,
                                      working_directory=self.directory.name)

        self.assertIn("spec", str(refused.exception))
        self.assertEqual(0, put.call_count)
        self.assertEqual(0, token.call_count)

    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_the_findings_of_a_refused_set_are_flattened_for_a_pipeline_to_annotate(self, put, token):
        put.return_value = _response(422, STRUCTURE_INVALID_BODY)

        outcome = upload_documentation_sets([SYSTEM_SET], DOC_SERVICE_URL, TOKEN_URI,
                                            "orders-doc-pipeline", "a-secret", PROVENANCE,
                                            working_directory=self.directory.name)

        self.assertEqual(1, len(outcome.findings))
        finding = outcome.findings[0]
        self.assertEqual("UNKNOWN_CHAPTER", finding.code)
        self.assertEqual("structure", finding.location)
        self.assertEqual("docs/4-runtime-view/reactions.md", finding.repository_path)

    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_a_set_that_went_through_has_no_findings(self, put, token):
        put.return_value = _response(201, STORED_BODY)

        outcome = upload_documentation_sets([SYSTEM_SET], DOC_SERVICE_URL, TOKEN_URI,
                                            "orders-doc-pipeline", "a-secret", PROVENANCE,
                                            working_directory=self.directory.name)

        self.assertEqual([], outcome.findings)

    @patch("jeap_pipeline.doc_upload.fetch_client_credentials_token", return_value="a-token")
    @patch("jeap_pipeline.doc_upload.requests.put")
    def test_the_upload_id_of_a_set_is_derived_from_the_seed(self, put, token):
        put.return_value = _response(201, STORED_BODY)

        upload_documentation_sets([SYSTEM_SET], DOC_SERVICE_URL, TOKEN_URI, "orders-doc-pipeline",
                                  "a-secret", PROVENANCE, upload_id_seed="example-org/repo/17/1",
                                  working_directory=self.directory.name)

        self.assertTrue(put.call_args[0][0].endswith(upload_id_of(SYSTEM_SET, "example-org/repo/17/1")))


class ReportTest(unittest.TestCase):

    def test_a_stored_set_says_what_happens_next(self):
        from jeap_pipeline.doc_upload import SetUploadOutcome, UploadResult

        report = format_set_upload_report(SetUploadOutcome(
            documentation_set=SYSTEM_SET, files=17, size_in_bytes=49356,
            result=UploadResult(upload_id="8f1c9a2e", status_code=201, id=42, state="PENDING")))

        self.assertIn("Uploading ./docs (system-docs, orders, arc42, markdown)", report)
        self.assertIn("17 file(s), 48.2 KB", report)
        self.assertIn("201 Created - upload 8f1c9a2e, state PENDING", report)
        self.assertIn("publishes it with its next build", report)

    def test_a_refused_set_renders_its_findings(self):
        from jeap_pipeline.doc_service_operations import StructureFinding, StructureReport
        from jeap_pipeline.doc_upload import SetUploadOutcome

        report = format_set_upload_report(SetUploadOutcome(
            documentation_set=SYSTEM_SET, files=17,
            structure=StructureReport(accepted=False, template="arc42", paths_checked=17,
                                      findings=[StructureFinding(
                                          code="UNKNOWN_CHAPTER",
                                          message="'4-runtime-view' is not a chapter of arc42.",
                                          path="4-runtime-view/reactions.md")])))

        self.assertIn("Uploading ./docs (system-docs, orders, arc42, markdown)", report)
        self.assertIn("UNKNOWN_CHAPTER", report)

    def test_a_set_that_had_been_stored_before_says_so(self):
        from jeap_pipeline.doc_upload import SetUploadOutcome, UploadResult

        report = format_set_upload_report(SetUploadOutcome(
            documentation_set=HTML_SET, files=2, size_in_bytes=2048,
            result=UploadResult(upload_id="8f1c9a2e", status_code=200, id=42, state="PENDING")))

        self.assertIn("Uploading ./html-docs/configuration-reference", report)
        self.assertIn("200 OK - upload 8f1c9a2e had already been stored", report)


if __name__ == "__main__":
    unittest.main()
