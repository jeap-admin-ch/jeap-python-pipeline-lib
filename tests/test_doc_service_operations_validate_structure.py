import json
import unittest
from unittest.mock import MagicMock, patch

import requests

from jeap_pipeline.doc_service_operations import (DocServiceError, DocServiceRequestError,
                                                  DocumentationSet,
                                                  validate_documentation_structure)

DOC_SERVICE_URL = "https://internal-csp.jme-dev.nivel.bazg.admin.ch/docs"

DOCUMENTATION_SET = DocumentationSet(path="./docs", type="system-docs", system="jme",
                                     template="arc42", source_format="markdown")

ACCEPTED_BODY = {
    "template": "arc42",
    "pathsChecked": 17,
    "pathsIgnored": 1,
    "allowedFolders": ["1-intro", "12-glossary"],
    "allowedExtensions": ["md", "png"],
    "findings": [],
    "findingsOmitted": 0,
}

REJECTED_BODY = {
    "type": "https://jeap.admin.ch/problems/docs/structure-invalid",
    "title": "The documentation structure is invalid",
    "status": 422,
    "detail": "2 problems in 17 paths.",
    "template": "arc42",
    "pathsChecked": 17,
    "pathsIgnored": 0,
    "allowedFolders": ["1-intro"],
    "allowedExtensions": ["md"],
    "findings": [
        {"code": "UNKNOWN_CHAPTER", "path": "4-runtime-view/reactions.md",
         "message": "'4-runtime-view' is not a chapter of arc42. Did you mean '6-runtime-view'?"},
        {"code": "EMPTY_TREE", "message": "Nothing in the set would be published."},
    ],
    "findingsOmitted": 3,
}


def _response(status_code, body=None, text=None):
    response = MagicMock()
    response.status_code = status_code
    response.text = text if text is not None else json.dumps(body or {})
    if body is None and text is not None:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = body or {}
    return response


class ValidateDocumentationStructureTest(unittest.TestCase):

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_calls_the_validation_endpoint_with_the_tree_as_the_body(self, post):
        post.return_value = _response(200, ACCEPTED_BODY)

        validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET,
                                         ["1-intro/goals.md", "12-glossary/glossary.md"])

        url = post.call_args[0][0]
        keyword_arguments = post.call_args[1]
        self.assertEqual(f"{DOC_SERVICE_URL}/api/uploads/docs/validation", url)
        self.assertEqual({"paths": ["1-intro/goals.md", "12-glossary/glossary.md"]},
                         json.loads(keyword_arguments["data"].decode("utf-8")))
        self.assertEqual(DOCUMENTATION_SET.validation_query_parameters(),
                         keyword_arguments["params"])
        self.assertEqual("Bearer a-token", keyword_arguments["headers"]["Authorization"])
        self.assertEqual("application/json", keyword_arguments["headers"]["Content-Type"])
        self.assertEqual((5, 60), keyword_arguments["timeout"])

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_trailing_slash_on_the_url_does_not_double_the_path(self, post):
        post.return_value = _response(200, ACCEPTED_BODY)

        validate_documentation_structure(DOC_SERVICE_URL + "/", "a-token", DOCUMENTATION_SET, [])

        self.assertEqual(f"{DOC_SERVICE_URL}/api/uploads/docs/validation", post.call_args[0][0])

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_200_is_an_accepted_report(self, post):
        post.return_value = _response(200, ACCEPTED_BODY)

        report = validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertTrue(report.accepted)
        self.assertEqual("arc42", report.template)
        self.assertEqual(17, report.paths_checked)
        self.assertEqual(1, report.paths_ignored)
        self.assertEqual(["1-intro", "12-glossary"], report.allowed_folders)
        self.assertEqual(["md", "png"], report.allowed_extensions)
        self.assertEqual([], report.findings)

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_422_is_a_rejected_report_and_not_an_exception(self, post):
        post.return_value = _response(422, REJECTED_BODY)

        report = validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertFalse(report.accepted)
        self.assertEqual(2, len(report.findings))
        self.assertEqual("UNKNOWN_CHAPTER", report.findings[0].code)
        self.assertEqual("4-runtime-view/reactions.md", report.findings[0].path)
        self.assertIsNone(report.findings[1].path, "a set-level finding is about the whole set")
        self.assertEqual(3, report.findings_omitted)
        self.assertEqual("2 problems in 17 paths.", report.detail)

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_400_names_the_problem_code_and_does_not_retry(self, post):
        post.return_value = _response(400, {"code": "UNKNOWN_PARAMETER",
                                            "detail": "'version' is not accepted here."})

        with self.assertRaises(DocServiceRequestError) as raised:
            validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertIn("UNKNOWN_PARAMETER", str(raised.exception))
        self.assertIn("'version' is not accepted here.", str(raised.exception))
        self.assertEqual(1, post.call_count)

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_403_names_the_role_the_client_needs(self, post):
        post.return_value = _response(403, {"detail": "Forbidden"})

        with self.assertRaises(DocServiceRequestError) as raised:
            validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertIn("%jme_@uploads_#write", str(raised.exception))

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_413_says_that_the_path_points_at_too_much(self, post):
        post.return_value = _response(413, {"code": "TOO_MANY_PATHS", "detail": "Too many."})

        with self.assertRaises(DocServiceRequestError) as raised:
            validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertIn("more paths than one validation may", str(raised.exception))

    @patch("jeap_pipeline.doc_service_operations.time.sleep")
    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_server_error_is_retried_and_then_raises(self, post, sleep):
        post.return_value = _response(503, text="Service Unavailable")

        with self.assertRaises(DocServiceError) as raised:
            validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [],
                                             attempts=3)

        self.assertEqual(3, post.call_count)
        self.assertEqual(2, sleep.call_count)
        self.assertIn("in 3 attempt(s)", str(raised.exception))

    @patch("jeap_pipeline.doc_service_operations.time.sleep")
    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_server_error_that_recovers_is_an_answer(self, post, sleep):
        post.side_effect = [_response(500, text="boom"), _response(200, ACCEPTED_BODY)]

        report = validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertTrue(report.accepted)
        self.assertEqual(2, post.call_count)

    @patch("jeap_pipeline.doc_service_operations.time.sleep")
    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_connection_error_is_retried(self, post, sleep):
        post.side_effect = requests.exceptions.ConnectionError("no route to host")

        with self.assertRaises(DocServiceError) as raised:
            validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [],
                                             attempts=2)

        self.assertEqual(2, post.call_count)
        self.assertIn("ConnectionError", str(raised.exception))

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_finding_code_this_library_does_not_know_is_reported_unchanged(self, post):
        # The codes are the doc service's API and it may add one; a report that dropped an
        # unrecognised finding would hide a problem the pipeline was asked about.
        post.return_value = _response(422, dict(REJECTED_BODY, findings=[
            {"code": "A_CODE_FROM_A_NEWER_DOC_SERVICE", "path": "1-intro/goals.md",
             "message": "Something this version has an opinion about."}]))

        report = validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertFalse(report.accepted)
        self.assertEqual("A_CODE_FROM_A_NEWER_DOC_SERVICE", report.findings[0].code)
        self.assertEqual("Something this version has an opinion about.", report.findings[0].message)

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_an_answer_that_is_not_json_raises(self, post):
        post.return_value = _response(200, text="<html>a proxy error page</html>")

        with self.assertRaises(DocServiceError) as raised:
            validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertIn("not JSON", str(raised.exception))


class MalformedAnswerTest(unittest.TestCase):
    """An answer nothing can be made of is this module's error, not a traceback out of it."""

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_json_that_is_not_an_object_raises(self, post):
        post.return_value = _response(200, ["not", "an", "object"])

        with self.assertRaises(DocServiceError) as raised:
            validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertIn("not an object", str(raised.exception))

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_count_that_is_not_a_number_raises(self, post):
        post.return_value = _response(200, dict(ACCEPTED_BODY, pathsChecked="many"))

        with self.assertRaises(DocServiceError) as raised:
            validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertIn("'pathsChecked' that is not a number", str(raised.exception))

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_a_count_that_is_absent_is_zero(self, post):
        post.return_value = _response(200, {"findings": []})

        report = validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertEqual(0, report.paths_checked)
        self.assertEqual(0, report.findings_omitted)

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_findings_that_are_not_a_list_of_objects_raise(self, post):
        # Dropping a finding this module cannot read would hide a problem it was asked about.
        post.return_value = _response(422, dict(REJECTED_BODY, findings=["UNKNOWN_CHAPTER"]))

        with self.assertRaises(DocServiceError) as raised:
            validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertIn("not a list of objects", str(raised.exception))

    @patch("jeap_pipeline.doc_service_operations.requests.post")
    def test_what_the_template_allows_is_printed_without_it_when_it_is_not_a_list(self, post):
        # The folders and the extensions are printed beside the findings; they are not the verdict.
        post.return_value = _response(200, dict(ACCEPTED_BODY, allowedFolders="1-intro"))

        report = validate_documentation_structure(DOC_SERVICE_URL, "a-token", DOCUMENTATION_SET, [])

        self.assertTrue(report.accepted)
        self.assertEqual([], report.allowed_folders)


if __name__ == "__main__":
    unittest.main()
