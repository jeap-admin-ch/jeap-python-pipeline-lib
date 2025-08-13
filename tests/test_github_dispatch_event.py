import json
import unittest
from unittest.mock import patch, MagicMock
from src.jeap_pipeline.github_dispatch_event import send_dispatch_event


class TestSendDispatchEvent(unittest.TestCase):

    @patch('src.jeap_pipeline.github_dispatch_event.requests.post')
    @patch('src.jeap_pipeline.github_dispatch_event.os.getenv')
    def test_send_dispatch_event_default_event_type(self, mock_getenv, mock_post):
        mock_getenv.return_value = 'fake_github_token'

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        send_dispatch_event('my-org', 'my-repo', 'dev', 'v1.0.0', ['service1', 'service2'])

        expected_url = 'https://api.github.com/repos/my-org/my-repo/dispatches'
        expected_payload = {
            'event_type': 'new-version-published',
            'client_payload': {
                'stage': 'dev',
                'services': ['service1', 'service2'],
                'version': 'v1.0.0'
            }
        }

        mock_post.assert_called_once_with(
            expected_url,
            headers={
                'Authorization': 'Bearer fake_github_token',
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28'
            },
            data=json.dumps(expected_payload)
        )

        mock_response.raise_for_status.assert_called_once()

    @patch('src.jeap_pipeline.github_dispatch_event.requests.post')
    @patch('src.jeap_pipeline.github_dispatch_event.os.getenv')
    def test_send_dispatch_event_undeploy_event_type(self, mock_getenv, mock_post):
        mock_getenv.return_value = 'fake_github_token'

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        send_dispatch_event(
            'my-org',
            'my-repo',
            'staging',
            'v2.0.0',
            ['serviceA'],
            event_type='undeploy'
        )

        expected_url = 'https://api.github.com/repos/my-org/my-repo/dispatches'
        expected_payload = {
            'event_type': 'undeploy',
            'client_payload': {
                'stage': 'staging',
                'services': ['serviceA'],
            }
        }

        mock_post.assert_called_once_with(
            expected_url,
            headers={
                'Authorization': 'Bearer fake_github_token',
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28'
            },
            data=json.dumps(expected_payload)
        )

        mock_response.raise_for_status.assert_called_once()


if __name__ == '__main__':
    unittest.main()
