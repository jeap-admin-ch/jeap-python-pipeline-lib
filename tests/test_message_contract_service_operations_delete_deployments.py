import unittest
from unittest.mock import patch, MagicMock
from requests.auth import HTTPBasicAuth

from src.jeap_pipeline.message_contract_service_operations import delete_deployments

class TestDeleteDeployment(unittest.TestCase):

    @patch('src.jeap_pipeline.message_contract_service_operations.requests.delete')
    def test_delete_deployment_success(self, mock_requests_delete):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_requests_delete.return_value = mock_response

        delete_deployments(
            mcs_url="http://mock-mcs-url",
            user="test_user",
            password="test_password",
            app_name="test_app",
            environment="test_env"
        )

        mock_requests_delete.assert_called_once_with(
            "http://mock-mcs-url/api/deployments/test_app/test_env",
            headers={"Accept": "application/json"},
            auth=HTTPBasicAuth('test_user', 'test_password')
        )

if __name__ == '__main__':
    unittest.main()
