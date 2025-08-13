import unittest
from unittest.mock import patch, MagicMock

from src.jeap_pipeline.ecs_undeployment_checker import (
    is_service_undeployed,
    wait_until_undeployment_has_finished
)


class TestECSUndeployment(unittest.TestCase):

    @patch('boto3.client')
    def test_is_service_undeployed_inactive(self, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_services.return_value = {
            'services': [{'status': 'INACTIVE'}],
            'failures': []
        }

        result = is_service_undeployed(mock_client, 'test-cluster', 'test-service')
        self.assertTrue(result)

    @patch('boto3.client')
    def test_is_service_undeployed_missing(self, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_services.return_value = {
            'services': [],
            'failures': [{'reason': 'MISSING'}]
        }

        result = is_service_undeployed(mock_client, 'test-cluster', 'test-service')
        self.assertTrue(result)

    @patch('boto3.client')
    def test_is_service_undeployed_unexpected_response(self, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_services.return_value = {
            'services': [{'status': 'ACTIVE'}],
            'failures': []
        }

        result = is_service_undeployed(mock_client, 'test-cluster', 'test-service')
        self.assertFalse(result)

    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_wait_until_undeployment_has_finished_success(self, mock_sleep, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        # Simulate service being ACTIVE first, then INACTIVE
        mock_client.describe_services.side_effect = [
            {'services': [{'status': 'ACTIVE'}], 'failures': []},
            {'services': [{'status': 'INACTIVE'}], 'failures': []}
        ]

        wait_until_undeployment_has_finished(
            cluster_name='test-cluster',
            service_name='test-service',
            aws_region='eu-central-1',
            interval=1,
            max_duration=5,
            verify_ssl=True
        )

    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_wait_until_undeployment_timeout(self, mock_sleep, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        # Always return ACTIVE to simulate timeout
        mock_client.describe_services.return_value = {
            'services': [{'status': 'ACTIVE'}],
            'failures': []
        }

        with self.assertRaises(Exception) as context:
            wait_until_undeployment_has_finished(
                cluster_name='test-cluster',
                service_name='test-service',
                aws_region='eu-central-1',
                interval=1,
                max_duration=3,
                verify_ssl=True
            )

        self.assertIn("did not complete", str(context.exception))


if __name__ == '__main__':
    unittest.main()
