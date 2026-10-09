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
            params=None,
            auth=HTTPBasicAuth('test_user', 'test_password')
        )

    @patch('src.jeap_pipeline.message_contract_service_operations.requests.put')
    def test_record_deployment_no_message_contracts(self, mock_requests_put):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_requests_put.return_value = mock_response

        record_deployment(
            mcs_url="http://mock-mcs-url",
            user="test_user",
            password="test_password",
            app_name="test_app",
            app_version="1.0.0",
            environment="test_env",
            no_message_contracts=True
        )

        mock_requests_put.assert_called_once_with(
            "http://mock-mcs-url/api/deployments/test_app/1.0.0/test_env",
            headers={"Content-Type": "application/json;charset=UTF-8"},
            params={"noMessageContracts": "true"},
            auth=HTTPBasicAuth('test_user', 'test_password')
        )

    @patch('src.jeap_pipeline.message_contract_service_operations.requests.put')
    def test_record_deployment_no_message_contracts_declaration_without_effect_raises(self, mock_requests_put):
        # the deployment has been ignored: the service does not support the declaration or the app name is unknown
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "Deployment ignored because appName and/or appVersion are unknown"
        mock_requests_put.return_value = mock_response

        with self.assertRaises(RuntimeError) as context:
            record_deployment(
                mcs_url="http://mock-mcs-url",
                user="test_user",
                password="test_password",
                app_name="test_app",
                app_version="1.0.0",
                environment="test_env",
                no_message_contracts=True
            )

        self.assertIn("test_app", str(context.exception))
        self.assertIn("12.11.0", str(context.exception))

if __name__ == '__main__':
    unittest.main()
