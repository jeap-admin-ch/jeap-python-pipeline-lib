import json
import unittest
from unittest.mock import patch, Mock

from src.jeap_pipeline import put_deployment_state, put_to_deployment_log_service, get_previous_deployment_on_environment

class TestDeploymentLogOperations(unittest.TestCase):
    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def test_put_deployment_state_success(self, mock_request):
        mock_request.return_value.status_code = 200
        response = put_deployment_state("http://example.com", "123", "DEPLOYED", "user", "pass")
        self.assertEqual(response.status_code, 200)

    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def test_put_deployment_state_with_message(self, mock_request):
        mock_request.return_value.status_code = 200
        response = put_deployment_state("http://example.com", "123", "DEPLOYED", "user", "pass", message="Deployment successful")
        self.assertEqual(response.status_code, 200)

    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def test_put_to_deployment_log_service_success(self, mock_request):
        mock_request.return_value.status_code = 200
        response = put_to_deployment_log_service("http://example.com", "123", {"key": "value"}, "user", "pass")
        self.assertEqual(response.status_code, 200)

    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def test_get_previous_deployment_on_environment_found(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"deployment": "data"})
        mock_request.return_value = mock_response
        response = get_previous_deployment_on_environment("http://example.com", "system", "component", "env", "1.0", "user", "pass")
        self.assertIsNotNone(response)
        self.assertEqual(response["deployment"], "data")

    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def test_get_previous_deployment_on_environment_not_found(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_request.return_value = mock_response
        response = get_previous_deployment_on_environment("http://example.com", "system", "component", "env", "1.0", "user", "pass")
        self.assertIsNone(response)