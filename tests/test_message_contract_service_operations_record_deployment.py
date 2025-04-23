import unittest, requests
from unittest.mock import patch, MagicMock

from requests.auth import HTTPBasicAuth

from src.jeap_pipeline.message_contract_service_operations import record_deployment


class TestRecordDeployment(unittest.TestCase):

    @patch('src.jeap_pipeline.message_contract_service_operations.requests.put')
    def test_record_deployment_success(self, mock_requests_put):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests_put.return_value = mock_response

        record_deployment(
            mcs_url="http://mock-mcs-url",
            user="test_user",
            password="test_password",
            app_name="test_app",
            app_version="1.0.0",
            environment="test_env"
        )

        mock_requests_put.assert_called_once_with(
            "http://mock-mcs-url/api/deployments/test_app/1.0.0/test_env",
            headers={"Content-Type": "application/json;charset=UTF-8"},
            auth=HTTPBasicAuth('test_user', 'test_password')
        )

if __name__ == '__main__':
    unittest.main()