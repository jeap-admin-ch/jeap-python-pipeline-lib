import unittest
from unittest.mock import patch, MagicMock

from requests import RequestException

from src.jeap_pipeline import (
    start_test_case,
    wait_until_test_case_ends,
    start_multiple_test_cases,
    NO_RESULT,
    PASS
)

class TestTestOrchestrator(unittest.TestCase):

    @patch("src.jeap_pipeline.test_orchestrator.requests.post")
    def test_start_test_case_success(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "test-id-123"
        test_id = start_test_case("test_case", "http://test-orchestrator-url")
        self.assertEqual(test_id, "test-id-123")



    @patch("src.jeap_pipeline.test_orchestrator.requests.post")
    def test_start_test_case_failure(self, mock_post):
        mock_post.side_effect = RequestException("Connection error")

        with self.assertRaises(ConnectionError) as context:
            start_test_case("test_case", "http://test-orchestrator-url", retry_count=1)

        self.assertIn("Failed to start test case", str(context.exception))



    @patch("src.jeap_pipeline.test_orchestrator.requests.get")
    def test_wait_until_test_case_ends_pass(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = '"PASS"'
        result = wait_until_test_case_ends("test-id", "http://test-orchestrator-url", timeout_minutes=1)
        self.assertEqual(result, PASS)

    @patch("src.jeap_pipeline.test_orchestrator.requests.get")
    def test_wait_until_test_case_ends_pass_2xx_response(self, mock_get):
        mock_get.return_value.status_code = 201
        mock_get.return_value.text = '"PASS"'
        result = wait_until_test_case_ends("test-id", "http://test-orchestrator-url", timeout_minutes=1)
        self.assertEqual(result, PASS)

    @patch("src.jeap_pipeline.test_orchestrator.requests.get")
    def test_wait_until_test_case_ends_timeout(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = '"NO_RESULT"'
        result = wait_until_test_case_ends("test-id", "http://test-orchestrator-url", timeout_minutes=0.001, sleep_interval=1)
        self.assertEqual(result, NO_RESULT)

    @patch("src.jeap_pipeline.test_orchestrator.requests.post")
    @patch("src.jeap_pipeline.test_orchestrator.requests.get")
    def test_start_multiple_test_cases_parallel(self, mock_get, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "test-id-1"
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = '"PASS"'
        results = start_multiple_test_cases(["test_case"], "http://test-orchestrator-url", run_sequential=False, timeout_minutes=1, sleep_interval_in_seconds=1)
        self.assertEqual(results, {"test-id-1": PASS})

    @patch("src.jeap_pipeline.test_orchestrator.requests.post")
    @patch("src.jeap_pipeline.test_orchestrator.requests.get")
    def test_start_multiple_test_cases_sequential(self, mock_get, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "test-id-2"
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = '"PASS"'
        results = start_multiple_test_cases(["test_case"], "http://test-orchestrator-url", run_sequential=True, timeout_minutes=1, sleep_interval_in_seconds=1)
        self.assertEqual(results, {"test-id-2": PASS})

if __name__ == "__main__":
    unittest.main()
