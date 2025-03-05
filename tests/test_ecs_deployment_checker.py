import unittest
from unittest.mock import patch, MagicMock

from src.jeap_pipeline.ecs_deployment_checker import (_get_primary_deployment,
                                                      _get_task_definition,
                                                      _check_image_version,
                                                      wait_until_new_deployment_has_occurred)


class TestECSDeployment(unittest.TestCase):

    @patch('boto3.client')
    def test_get_primary_deployment(self, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_services.return_value = {
            'services': [{
                'deployments': [
                    {'status': 'PRIMARY', 'rolloutState': 'COMPLETED', 'taskDefinition': 'arn:aws:ecs:task-definition/123'}
                ]
            }]
        }
        cluster_name = 'test-cluster'
        service_name = 'test-service'
        primary_deployment = _get_primary_deployment(mock_client, cluster_name, service_name)
        self.assertIsNotNone(primary_deployment)
        self.assertEqual(primary_deployment['status'], 'PRIMARY')

    @patch('boto3.client')
    def test_get_task_definition(self, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{'image': 'test-image:latest'}]
            }
        }
        task_definition_arn = 'arn:aws:ecs:task-definition/123'
        task_definition = _get_task_definition(mock_client, task_definition_arn)
        self.assertIsNotNone(task_definition)
        self.assertEqual(task_definition['containerDefinitions'][0]['image'], 'test-image:latest')

    def test_check_image_version(self):
        task_definition = {
            'containerDefinitions': [{'image': 'test-image:latest'}]
        }
        expected_image_version = 'latest'
        result = _check_image_version(task_definition, expected_image_version)
        self.assertTrue(result)

    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_wait_until_new_deployment_has_occurred(self, mock_sleep, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_services.return_value = {
            'services': [{
                'deployments': [
                    {'status': 'PRIMARY', 'rolloutState': 'COMPLETED', 'taskDefinition': 'arn:aws:ecs:task-definition/123'}
                ]
            }]
        }
        mock_client.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{'image': 'test-image:latest'}]
            }
        }

        cluster_name = 'test-cluster'
        service_name = 'test-service'
        expected_image_version = 'latest'
        aws_region = 'eu-central-2'
        interval = 1
        max_duration = 10
        verify_ssl = True

        result = wait_until_new_deployment_has_occurred(cluster_name, service_name, expected_image_version, aws_region, interval, max_duration, verify_ssl)
        self.assertEqual(result, 'arn:aws:ecs:task-definition/123')


if __name__ == '__main__':
    unittest.main()
