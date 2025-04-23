import unittest, requests
from unittest.mock import patch, MagicMock

from requests.auth import HTTPBasicAuth

from src.jeap_pipeline.message_contract_service_operations import get_compatibility, CompatibilityResult


class TestGetCompatibility(unittest.TestCase):

    @patch('src.jeap_pipeline.message_contract_service_operations.requests.get')
    def test_get_compatibility_success(self, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "compatible": True,
            "message": "Compatibility check passed"
        }
        mock_requests_get.return_value = mock_response

        result = get_compatibility(
            mcs_url="http://mock-mcs-url",
            user="test_user",
            password="test_password",
            app_name="test_app",
            app_version="1.0.0",
            environment="test_env"
        )

        self.assertIsInstance(result, CompatibilityResult)
        self.assertTrue(result.compatible)
        self.assertEqual(result.message, "Compatibility check passed")

        mock_requests_get.assert_called_once_with(
            "http://mock-mcs-url/api/deployments/compatibility/test_app/1.0.0/test_env",
            headers={"Accept": "application/json"},
            auth=HTTPBasicAuth('test_user', 'test_password')
        )

    @patch('src.jeap_pipeline.message_contract_service_operations.requests.get')
    def test_get_compatibility_failure(self, mock_requests_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "compatible": False,
            "message": "Compatibility check failed"
        }
        mock_requests_get.return_value = mock_response

        result = get_compatibility(
                mcs_url="http://mock-mcs-url",
                user="test_user",
                password="test_password",
                app_name="test_app",
                app_version="1.0.0",
                environment="test_env"
            )

        mock_requests_get.assert_called_once_with(
            "http://mock-mcs-url/api/deployments/compatibility/test_app/1.0.0/test_env",
            headers={"Accept": "application/json"},
            auth=HTTPBasicAuth('test_user', 'test_password')
        )

        self.assertFalse(result.compatible)
        self.assertEqual(result.message, "Compatibility check failed")

if __name__ == '__main__':
    unittest.main()