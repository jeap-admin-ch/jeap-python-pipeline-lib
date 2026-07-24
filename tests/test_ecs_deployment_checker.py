import unittest
from unittest.mock import patch, MagicMock

from src.jeap_pipeline.ecs_deployment_checker import (_get_primary_deployment,
                                                      _get_task_definition,
                                                      wait_until_deployments_completed,
                                                      get_deployment_status,
                                                      WAITING_FOR_ROLLOUT,
                                                      ROLLOUT_IN_PROGRESS,
                                                      ROLLOUT_COMPLETED,
                                                      ROLLOUT_FAILED,
                                                      STATE_UNKNOWN)


def _service_response(rollout_state, task_definition_arn, running=0, desired=1, pending=1, failed=0):
    return {
        'services': [{
            'deployments': [
                {'status': 'PRIMARY', 'rolloutState': rollout_state, 'taskDefinition': task_definition_arn,
                 'runningCount': running, 'desiredCount': desired, 'pendingCount': pending, 'failedTasks': failed}
            ]
        }]
    }


def _scripted_describe_services(script):
    """script: dict service_name -> list of responses; the last response repeats forever."""
    counters = {}

    def side_effect(cluster=None, services=None):
        name = services[0]
        index = counters.get(name, 0)
        counters[name] = index + 1
        responses = script[name]
        return responses[min(index, len(responses) - 1)]

    return side_effect


def _task_definition_side_effect(images_by_arn):
    def side_effect(taskDefinition=None):
        return {'taskDefinition': {'containerDefinitions': [{'image': images_by_arn[taskDefinition]}]}}

    return side_effect


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


class TestGetDeploymentStatus(unittest.TestCase):

    def _client(self, response, image='registry/repo:1.0.0'):
        mock_client = MagicMock()
        mock_client.describe_services.return_value = response
        mock_client.describe_task_definition.side_effect = _task_definition_side_effect(
            {'arn:aws:ecs:task-definition/123': image})
        return mock_client

    def test_old_image_with_completed_rollout_is_waiting_for_rollout(self):
        # The PRIMARY deployment still runs the previous image: its rollout state COMPLETED
        # refers to the old deployment and must not be reported as completed.
        client = self._client(_service_response('COMPLETED', 'arn:aws:ecs:task-definition/123', running=1, pending=0),
                              image='registry/repo:0.0.1-old')
        status = get_deployment_status(client, 'cluster', 'service', '0.0.2-new')
        self.assertEqual(status.state, WAITING_FOR_ROLLOUT)
        self.assertEqual(status.current_image_tag, '0.0.1-old')

    def test_new_image_in_progress(self):
        client = self._client(_service_response('IN_PROGRESS', 'arn:aws:ecs:task-definition/123'),
                              image='registry/repo:0.0.2-new')
        status = get_deployment_status(client, 'cluster', 'service', '0.0.2-new')
        self.assertEqual(status.state, ROLLOUT_IN_PROGRESS)
        self.assertEqual(status.running, 0)
        self.assertEqual(status.pending, 1)

    def test_new_image_completed(self):
        client = self._client(_service_response('COMPLETED', 'arn:aws:ecs:task-definition/123', running=1, pending=0),
                              image='registry/repo:0.0.2-new')
        status = get_deployment_status(client, 'cluster', 'service', '0.0.2-new')
        self.assertEqual(status.state, ROLLOUT_COMPLETED)
        self.assertEqual(status.task_definition_arn, 'arn:aws:ecs:task-definition/123')

    def test_new_image_failed(self):
        client = self._client(_service_response('FAILED', 'arn:aws:ecs:task-definition/123', failed=2),
                              image='registry/repo:0.0.2-new')
        status = get_deployment_status(client, 'cluster', 'service', '0.0.2-new')
        self.assertEqual(status.state, ROLLOUT_FAILED)
        self.assertEqual(status.failed_tasks, 2)

    def test_no_primary_deployment_is_unknown(self):
        client = MagicMock()
        client.describe_services.return_value = {'services': [{'deployments': []}]}
        status = get_deployment_status(client, 'cluster', 'service', '0.0.2-new')
        self.assertEqual(status.state, STATE_UNKNOWN)

    def test_image_cache_avoids_repeated_task_definition_lookups(self):
        client = self._client(_service_response('IN_PROGRESS', 'arn:aws:ecs:task-definition/123'),
                              image='registry/repo:0.0.2-new')
        cache = {}
        get_deployment_status(client, 'cluster', 'service', '0.0.2-new', cache)
        get_deployment_status(client, 'cluster', 'service', '0.0.2-new', cache)
        self.assertEqual(client.describe_task_definition.call_count, 1)


class TestWaitUntilDeploymentsCompleted(unittest.TestCase):

    IMAGES = {
        'arn:old': 'registry/repo:0.0.1-old',
        'arn:new-1': 'registry/repo:0.0.2-new',
        'arn:new-2': 'registry/repo:0.0.2-new',
    }

    @patch('builtins.print')
    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_two_services_full_lifecycle(self, mock_sleep, mock_boto_client, mock_print):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        lifecycle = lambda arn: [
            _service_response('COMPLETED', 'arn:old', running=1, pending=0),
            _service_response('IN_PROGRESS', arn, running=0, pending=1),
            _service_response('IN_PROGRESS', arn, running=1, pending=0),
            _service_response('COMPLETED', arn, running=1, pending=0),
        ]
        mock_client.describe_services.side_effect = _scripted_describe_services(
            {'service-one': lifecycle('arn:new-1'), 'svc-2': lifecycle('arn:new-2')})
        mock_client.describe_task_definition.side_effect = _task_definition_side_effect(self.IMAGES)

        result = wait_until_deployments_completed('test-cluster', ['service-one', 'svc-2'], '0.0.2-new',
                                                  'eu-central-2', interval=1, max_duration=10)

        self.assertEqual(result, {'service-one': 'arn:new-1', 'svc-2': 'arn:new-2'})
        lines = [c.args[0] for c in mock_print.call_args_list]
        self.assertIn('Waiting for image 0.0.2-new on cluster test-cluster (timeout 0m10s)', lines)
        self.assertIn('[00:00] service-one  waiting for rollout (still on 0.0.1-old)', lines)
        self.assertIn('[00:00] svc-2        waiting for rollout (still on 0.0.1-old)', lines)
        self.assertIn('[00:01] service-one  rollout started (running 0/1, pending 1)', lines)
        self.assertIn('[00:02] service-one  rollout in progress (running 1/1, pending 0)', lines)
        self.assertIn('[00:03] service-one  rollout completed after 0m03s', lines)
        self.assertIn('[00:03] svc-2        rollout completed after 0m03s', lines)
        self.assertEqual(lines[-1], 'All 2 services deployed 0.0.2-new')

    @patch('builtins.print')
    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_unchanged_state_is_logged_only_once(self, mock_sleep, mock_boto_client, mock_print):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_services.side_effect = _scripted_describe_services(
            {'service-one': [_service_response('COMPLETED', 'arn:old', running=1, pending=0)]})
        mock_client.describe_task_definition.side_effect = _task_definition_side_effect(self.IMAGES)

        with self.assertRaises(Exception):
            wait_until_deployments_completed('test-cluster', ['service-one'], '0.0.2-new', 'eu-central-2',
                                             interval=1, max_duration=10, heartbeat_interval=100)

        waiting_lines = [c.args[0] for c in mock_print.call_args_list if 'waiting for rollout' in c.args[0]]
        self.assertEqual(waiting_lines, ['[00:00] service-one  waiting for rollout (still on 0.0.1-old)'])

    @patch('builtins.print')
    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_heartbeat_while_nothing_changes(self, mock_sleep, mock_boto_client, mock_print):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_services.side_effect = _scripted_describe_services(
            {'service-one': [_service_response('COMPLETED', 'arn:old', running=1, pending=0)]})
        mock_client.describe_task_definition.side_effect = _task_definition_side_effect(self.IMAGES)

        with self.assertRaises(Exception):
            wait_until_deployments_completed('test-cluster', ['service-one'], '0.0.2-new', 'eu-central-2',
                                             interval=1, max_duration=10, heartbeat_interval=4)

        heartbeat_lines = [c.args[0] for c in mock_print.call_args_list if 'still waiting' in c.args[0]]
        self.assertEqual(heartbeat_lines, ['[00:04] still waiting for rollout: 1 service',
                                           '[00:08] still waiting for rollout: 1 service'])

    @patch('builtins.print')
    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_timeout_reports_incomplete_services_with_state(self, mock_sleep, mock_boto_client, mock_print):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_services.side_effect = _scripted_describe_services({
            'service-one': [_service_response('COMPLETED', 'arn:new-1', running=1, pending=0)],
            'svc-2': [_service_response('IN_PROGRESS', 'arn:new-2', running=0, pending=1)],
        })
        mock_client.describe_task_definition.side_effect = _task_definition_side_effect(self.IMAGES)

        with self.assertRaises(Exception) as context:
            wait_until_deployments_completed('test-cluster', ['service-one', 'svc-2'], '0.0.2-new',
                                             'eu-central-2', interval=1, max_duration=3)

        message = str(context.exception)
        self.assertIn('did not complete within 0m03s', message)
        self.assertIn('svc-2 (rollout in progress (running 0/1, pending 1))', message)
        self.assertNotIn('service-one (', message)


if __name__ == '__main__':
    unittest.main()
