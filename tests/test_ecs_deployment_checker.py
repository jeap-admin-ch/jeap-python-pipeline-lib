import unittest
from unittest.mock import patch, MagicMock

from src.jeap_pipeline.ecs_deployment_checker import (_get_primary_deployment,
                                                      _get_task_definition,
                                                      _check_image_version,
                                                      _describe_deployment_state,
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

    def test_describe_deployment_state(self):
        mock_client = MagicMock()
        mock_client.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{'image': 'test-image:1.2.3'}]
            }
        }
        primary_deployment = {
            'status': 'PRIMARY',
            'rolloutState': 'IN_PROGRESS',
            'taskDefinition': 'arn:aws:ecs:task-definition/123',
            'runningCount': 1,
            'desiredCount': 2,
            'pendingCount': 1,
            'failedTasks': 0
        }
        state = _describe_deployment_state(mock_client, primary_deployment)
        self.assertEqual(state, "rollout IN_PROGRESS (running 1/2, pending 1, failed 0), current image test-image:1.2.3")

    def test_describe_deployment_state_without_primary_deployment(self):
        state = _describe_deployment_state(MagicMock(), {})
        self.assertEqual(state, "no PRIMARY deployment found")

    def test_describe_deployment_state_tolerates_task_definition_error(self):
        mock_client = MagicMock()
        mock_client.describe_task_definition.side_effect = RuntimeError("boom")
        primary_deployment = {
            'status': 'PRIMARY',
            'rolloutState': 'IN_PROGRESS',
            'taskDefinition': 'arn:aws:ecs:task-definition/123'
        }
        state = _describe_deployment_state(mock_client, primary_deployment)
        self.assertEqual(state, "rollout IN_PROGRESS (running ?/?, pending ?, failed ?), current image unknown")

    @patch('builtins.print')
    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_wait_logs_progress_while_deployment_in_progress(self, mock_sleep, mock_boto_client, mock_print):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        in_progress = {
            'services': [{
                'deployments': [
                    {'status': 'PRIMARY', 'rolloutState': 'IN_PROGRESS', 'taskDefinition': 'arn:aws:ecs:task-definition/123',
                     'runningCount': 0, 'desiredCount': 1, 'pendingCount': 1, 'failedTasks': 0}
                ]
            }]
        }
        completed = {
            'services': [{
                'deployments': [
                    {'status': 'PRIMARY', 'rolloutState': 'COMPLETED', 'taskDefinition': 'arn:aws:ecs:task-definition/124'}
                ]
            }]
        }
        mock_client.describe_services.side_effect = [in_progress, in_progress, completed]
        mock_client.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{'image': 'test-image:latest'}]
            }
        }

        result = wait_until_new_deployment_has_occurred(
            'test-cluster', 'test-service', 'latest', 'eu-central-2',
            interval=1, max_duration=10, progress_interval=1)

        self.assertEqual(result, 'arn:aws:ecs:task-definition/124')
        progress_lines = [c.args[0] for c in mock_print.call_args_list if 'Waiting for deployment' in c.args[0]]
        self.assertEqual(len(progress_lines), 2)
        self.assertIn('[test-service]', progress_lines[0])
        self.assertIn('expected image version latest', progress_lines[0])
        self.assertIn('rollout IN_PROGRESS (running 0/1, pending 1, failed 0), current image test-image:latest',
                      progress_lines[0])

    @patch('builtins.print')
    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_wait_throttles_progress_logging_to_progress_interval(self, mock_sleep, mock_boto_client, mock_print):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_services.return_value = {
            'services': [{
                'deployments': [
                    {'status': 'PRIMARY', 'rolloutState': 'IN_PROGRESS', 'taskDefinition': 'arn:aws:ecs:task-definition/123'}
                ]
            }]
        }
        mock_client.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{'image': 'test-image:1.2.3'}]
            }
        }

        # 13 polls at interval=5 with progress_interval=30 -> logged on polls 0, 6 and 12
        with self.assertRaises(Exception):
            wait_until_new_deployment_has_occurred(
                'test-cluster', 'test-service', 'latest', 'eu-central-2',
                interval=5, max_duration=60, progress_interval=30)

        progress_lines = [c.args[0] for c in mock_print.call_args_list if 'Waiting for deployment' in c.args[0]]
        self.assertEqual(len(progress_lines), 3)

    @patch('builtins.print')
    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_wait_does_not_log_progress_on_immediate_success(self, mock_sleep, mock_boto_client, mock_print):
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

        wait_until_new_deployment_has_occurred(
            'test-cluster', 'test-service', 'latest', 'eu-central-2',
            interval=1, max_duration=10)

        progress_lines = [c.args[0] for c in mock_print.call_args_list if 'Waiting for deployment' in c.args[0]]
        self.assertEqual(progress_lines, [])
        mock_print.assert_called_once_with('[test-service] Deployment completed with image version latest', flush=True)


if __name__ == '__main__':
    unittest.main()
