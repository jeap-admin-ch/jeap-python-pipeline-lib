import unittest
from unittest.mock import patch
from requests.auth import HTTPBasicAuth

from src.jeap_pipeline import (post_openapi_spec_to_archrepo_service)

class TestArchRepoOperations(unittest.TestCase):

    @patch('src.jeap_pipeline.archrepo_operations.request')
    def test_put_to_deployment_log_service_success(self, mock_request):
        mock_request.return_value.status_code = 200
        response = post_openapi_spec_to_archrepo_service(
            "https://example.com",
            "my-system",
            "my-component",
            "the-version",
            {"key": "value"},
            "user",
            "pass"
        )
        mock_request.assert_called_with(
            'POST',
            'https://example.com/api/openapi/my-system/my-component?version=the-version',
            files={'file': ('openapi.json', '{"key": "value"}', 'application/json')},
            auth=HTTPBasicAuth('user', 'pass')
        )
        self.assertEqual(response.status_code, 200)