import unittest
from botocore.exceptions import ClientError
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from src.jeap_pipeline.ecs_deployment_checker import (_get_primary_deployment,
                                                      _get_task_definition,
                                                      wait_until_deployments_completed,
                                                      get_deployment_status,
                                                      get_failure_diagnostics,
                                                      build_cloudwatch_log_stream_url,
                                                      DeploymentFailedError,
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

    def test_image_tag_is_compared_exactly(self):
        client = self._client(_service_response('COMPLETED', 'arn:aws:ecs:task-definition/123'),
                              image='registry/repo:11.2.3')

        status = get_deployment_status(client, 'cluster', 'service', '1.2.3')

        self.assertEqual(status.state, WAITING_FOR_ROLLOUT)
        self.assertEqual(status.current_image_tag, '11.2.3')

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


class TestGetFailureDiagnostics(unittest.TestCase):

    TASK_DEFINITION_ARN = 'arn:aws:ecs:eu-central-2:123:task-definition/service:42'

    def _ecs_client(self):
        client = MagicMock()
        client.describe_services.return_value = _service_response(
            'FAILED', self.TASK_DEFINITION_ARN, failed=1)
        client.describe_task_definition.return_value = {
            'taskDefinition': {
                'containerDefinitions': [{
                    'name': 'application',
                    'image': 'registry/repo:0.0.2-new',
                    'logConfiguration': {
                        'logDriver': 'awslogs',
                        'options': {
                            'awslogs-group': '/ecs/application',
                            'awslogs-region': 'eu-central-1',
                            'awslogs-stream-prefix': 'ecs',
                        },
                    },
                }],
            },
        }
        client.list_tasks.return_value = {
            'taskArns': ['arn:aws:ecs:eu-central-2:123:task/cluster/old',
                         'arn:aws:ecs:eu-central-2:123:task/cluster/latest',
                         'arn:aws:ecs:eu-central-2:123:task/cluster/other-revision'],
        }
        client.describe_tasks.return_value = {
            'tasks': [
                {
                    'taskArn': 'arn:aws:ecs:eu-central-2:123:task/cluster/old',
                    'taskDefinitionArn': self.TASK_DEFINITION_ARN,
                    'stoppedAt': datetime(2026, 8, 19, tzinfo=timezone.utc),
                },
                {
                    'taskArn': 'arn:aws:ecs:eu-central-2:123:task/cluster/latest',
                    'taskDefinitionArn': self.TASK_DEFINITION_ARN,
                    'stoppedAt': datetime(2026, 8, 20, tzinfo=timezone.utc),
                    'stopCode': 'EssentialContainerExited',
                    'stoppedReason': 'Essential container in task exited',
                    'containers': [{
                        'name': 'application',
                        'exitCode': 1,
                        'reason': 'OutOfMemoryError',
                        'lastStatus': 'STOPPED',
                    }],
                },
                {
                    'taskArn': 'arn:aws:ecs:eu-central-2:123:task/cluster/other-revision',
                    'taskDefinitionArn': 'arn:other-task-definition',
                    'stoppedAt': datetime(2026, 8, 21, tzinfo=timezone.utc),
                },
            ],
        }
        return client

    @patch('boto3.client')
    def test_collects_latest_stopped_task_container_and_optional_logs(self, mock_boto_client):
        ecs_client = self._ecs_client()
        logs_client = MagicMock()
        logs_client.get_log_events.return_value = {
            'events': [{'timestamp': 123, 'ingestionTime': 456, 'message': 'startup failed'}],
        }
        mock_boto_client.side_effect = lambda service, **kwargs: {
            'ecs': ecs_client, 'logs': logs_client}[service]

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2',
                                         include_logs=True, log_event_limit=25)

        service = result.services[0]
        self.assertEqual(service.service_name, 'service')
        self.assertEqual(service.deployment_status.state, ROLLOUT_FAILED)
        self.assertEqual(service.stopped_task.task_arn,
                         'arn:aws:ecs:eu-central-2:123:task/cluster/latest')
        self.assertEqual(service.stopped_task.stop_code, 'EssentialContainerExited')
        self.assertEqual(service.stopped_task.stopped_reason, 'Essential container in task exited')
        container = service.stopped_task.containers[0]
        self.assertEqual(container.exit_code, 1)
        self.assertEqual(container.reason, 'OutOfMemoryError')
        self.assertEqual(container.log_group, '/ecs/application')
        self.assertEqual(container.log_stream, 'ecs/application/latest')
        self.assertEqual(container.log_region, 'eu-central-1')
        self.assertTrue(container.has_awslogs_configuration)
        self.assertEqual(
            container.cloudwatch_log_url,
            'https://eu-central-1.console.aws.amazon.com/cloudwatch/home?region=eu-central-1'
            '#logsV2:log-groups/log-group/$252Fecs$252Fapplication/log-events/'
            'ecs$252Fapplication$252Flatest')
        self.assertEqual(container.log_events[0].message, 'startup failed')
        logs_client.get_log_events.assert_called_once_with(
            logGroupName='/ecs/application', logStreamName='ecs/application/latest',
            limit=25, startFromHead=False)
        self.assertEqual(mock_boto_client.call_args_list[-1].kwargs['region_name'], 'eu-central-1')

    @patch('boto3.client')
    def test_does_not_load_logs_by_default(self, mock_boto_client):
        ecs_client = self._ecs_client()
        mock_boto_client.return_value = ecs_client

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2')

        container = result.services[0].stopped_task.containers[0]
        self.assertEqual(container.log_events, [])
        self.assertEqual(container.errors, [])
        self.assertTrue(container.has_awslogs_configuration)
        self.assertIsNotNone(container.cloudwatch_log_url)
        mock_boto_client.assert_called_once_with('ecs', region_name='eu-central-2', verify=True)

    @patch('boto3.client')
    def test_aws_injected_container_without_awslogs_configuration_has_no_log_error(self,
                                                                                   mock_boto_client):
        ecs_client = self._ecs_client()
        ecs_client.describe_tasks.return_value['tasks'][1]['containers'].append({
            'name': 'aws-guardduty-agent-123456',
            'exitCode': 137,
            'reason': 'Container stopped by runtime',
            'lastStatus': 'STOPPED',
        })
        logs_client = MagicMock()
        logs_client.get_log_events.return_value = {'events': []}
        mock_boto_client.side_effect = lambda service, **kwargs: {
            'ecs': ecs_client, 'logs': logs_client}[service]

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2',
                                         include_logs=True)

        containers = result.services[0].stopped_task.containers
        injected_container = next(container for container in containers
                                  if container.name == 'aws-guardduty-agent-123456')
        self.assertFalse(injected_container.has_awslogs_configuration)
        self.assertIsNone(injected_container.cloudwatch_log_url)
        self.assertEqual(injected_container.errors, [])
        self.assertEqual(injected_container.exit_code, 137)
        self.assertEqual(injected_container.reason, 'Container stopped by runtime')
        logs_client.get_log_events.assert_called_once()

    @patch('boto3.client')
    def test_missing_log_group_with_awslogs_configuration_is_an_error(self, mock_boto_client):
        ecs_client = self._ecs_client()
        log_options = ecs_client.describe_task_definition.return_value[
            'taskDefinition']['containerDefinitions'][0]['logConfiguration']['options']
        del log_options['awslogs-group']
        mock_boto_client.return_value = ecs_client

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2',
                                         include_logs=True)

        container = result.services[0].stopped_task.containers[0]
        self.assertTrue(container.has_awslogs_configuration)
        self.assertIsNone(container.cloudwatch_log_url)
        self.assertEqual(
            container.errors,
            ['CloudWatch log group or stream could not be determined'])

    @patch('boto3.client')
    def test_incomplete_awslogs_configuration_is_not_an_error_when_logs_are_not_requested(
            self, mock_boto_client):
        ecs_client = self._ecs_client()
        log_options = ecs_client.describe_task_definition.return_value[
            'taskDefinition']['containerDefinitions'][0]['logConfiguration']['options']
        del log_options['awslogs-group']
        mock_boto_client.return_value = ecs_client

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2',
                                         include_logs=False)

        container = result.services[0].stopped_task.containers[0]
        self.assertTrue(container.has_awslogs_configuration)
        self.assertIsNone(container.cloudwatch_log_url)
        self.assertEqual(container.errors, [])

    @patch('boto3.client')
    def test_log_access_failure_does_not_hide_ecs_diagnostics(self, mock_boto_client):
        ecs_client = self._ecs_client()
        logs_client = MagicMock()
        logs_client.get_log_events.side_effect = PermissionError('logs:GetLogEvents denied')
        mock_boto_client.side_effect = lambda service, **kwargs: {
            'ecs': ecs_client, 'logs': logs_client}[service]

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2',
                                         include_logs=True)

        task = result.services[0].stopped_task
        self.assertEqual(task.stopped_reason, 'Essential container in task exited')
        self.assertEqual(task.containers[0].log_events, [])
        self.assertIn('logs:GetLogEvents denied', task.containers[0].errors[0])

    @patch('boto3.client')
    def test_list_tasks_failure_is_returned_as_service_error(self, mock_boto_client):
        ecs_client = self._ecs_client()
        ecs_client.list_tasks.side_effect = PermissionError('ecs:ListTasks denied')
        mock_boto_client.return_value = ecs_client

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2')

        service = result.services[0]
        self.assertEqual(service.deployment_status.state, ROLLOUT_FAILED)
        self.assertIsNone(service.stopped_task)
        self.assertEqual(len(service.errors), 1)
        self.assertIn('ecs:ListTasks denied', service.errors[0])

    @patch('boto3.client')
    def test_successful_lookup_without_matching_task_is_reported(self, mock_boto_client):
        ecs_client = self._ecs_client()
        ecs_client.list_tasks.return_value = {'taskArns': []}
        mock_boto_client.return_value = ecs_client

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2')

        service = result.services[0]
        self.assertEqual(service.errors,
                         ['No stopped ECS task found for the deployment task definition'])

    @patch('boto3.client')
    def test_rejects_log_event_limit_outside_cloudwatch_range(self, mock_boto_client):
        for invalid_limit in (0, 10_001):
            with self.subTest(log_event_limit=invalid_limit):
                with self.assertRaisesRegex(ValueError, 'between 1 and 10000'):
                    get_failure_diagnostics('cluster', ['service'], 'version', 'eu-central-2',
                                            log_event_limit=invalid_limit)
        mock_boto_client.assert_not_called()

    @patch('boto3.client')
    def test_waiting_for_rollout_does_not_diagnose_old_primary_task_definition(self, mock_boto_client):
        ecs_client = self._ecs_client()
        ecs_client.describe_task_definition.return_value['taskDefinition']['containerDefinitions'][0][
            'image'] = 'registry/repo:0.0.1-old'
        mock_boto_client.return_value = ecs_client

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2',
                                         include_logs=True)

        service = result.services[0]
        self.assertEqual(service.deployment_status.state, WAITING_FOR_ROLLOUT)
        self.assertIsNone(service.stopped_task)
        self.assertIn('did not become PRIMARY', service.errors[0])
        ecs_client.list_tasks.assert_not_called()

    @patch('boto3.client')
    def test_unknown_deployment_state_skips_stopped_task_diagnostics(self, mock_boto_client):
        ecs_client = self._ecs_client()
        ecs_client.describe_task_definition.side_effect = PermissionError('cannot read task definition')
        mock_boto_client.return_value = ecs_client

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2')

        service = result.services[0]
        self.assertEqual(service.deployment_status.state, STATE_UNKNOWN)
        self.assertEqual(service.errors,
                         ['Deployment state is unknown; stopped-task diagnostics were skipped'])
        ecs_client.list_tasks.assert_not_called()

    @patch('boto3.client')
    def test_completed_rollout_needs_no_failure_diagnostics(self, mock_boto_client):
        ecs_client = self._ecs_client()
        ecs_client.describe_services.return_value = _service_response(
            'COMPLETED', self.TASK_DEFINITION_ARN, running=1, pending=0)
        mock_boto_client.return_value = ecs_client

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2')

        service = result.services[0]
        self.assertEqual(service.deployment_status.state, ROLLOUT_COMPLETED)
        self.assertIsNone(service.stopped_task)
        self.assertEqual(service.errors, [])
        ecs_client.list_tasks.assert_not_called()

    @patch('boto3.client')
    def test_in_progress_rollout_is_diagnosed(self, mock_boto_client):
        ecs_client = self._ecs_client()
        ecs_client.describe_services.return_value = _service_response(
            'IN_PROGRESS', self.TASK_DEFINITION_ARN)
        mock_boto_client.return_value = ecs_client

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2')

        self.assertEqual(result.services[0].deployment_status.state, ROLLOUT_IN_PROGRESS)
        self.assertIsNotNone(result.services[0].stopped_task)

    @patch('boto3.client')
    def test_stopped_task_without_containers_is_reported(self, mock_boto_client):
        ecs_client = self._ecs_client()
        ecs_client.describe_tasks.return_value['tasks'][1]['containers'] = []
        mock_boto_client.return_value = ecs_client

        result = get_failure_diagnostics('cluster', ['service'], '0.0.2-new', 'eu-central-2')

        task = result.services[0].stopped_task
        self.assertEqual(task.containers, [])
        self.assertIn('no container details', task.errors[-1])

    @patch('boto3.client')
    def test_status_snapshot_preserves_failed_task_definition_after_rollback(self, mock_boto_client):
        ecs_client = self._ecs_client()
        ecs_client.describe_services.return_value = _service_response(
            'COMPLETED', 'arn:old-task-definition', running=1, pending=0)
        mock_boto_client.return_value = ecs_client
        failed_status = get_deployment_status(
            self._ecs_client(), 'cluster', 'service', '0.0.2-new')

        result = get_failure_diagnostics(
            'cluster', ['service'], '0.0.2-new', 'eu-central-2',
            deployment_statuses={'service': failed_status})

        service = result.services[0]
        self.assertIs(service.deployment_status, failed_status)
        self.assertEqual(service.deployment_status.state, ROLLOUT_FAILED)
        self.assertEqual(service.stopped_task.task_definition_arn, self.TASK_DEFINITION_ARN)
        ecs_client.describe_services.assert_not_called()


class TestBuildCloudWatchLogStreamUrl(unittest.TestCase):

    def test_builds_direct_cloudwatch_log_stream_url(self):
        url = build_cloudwatch_log_stream_url(
            'eu-central-2',
            '/aws/ecs/jme-nivel-process-context-app-service',
            'jme-nivel-process-context-app-service/'
            'jme-nivel-process-context-app-service/e7d0615da0574864a734b260147aed77')

        self.assertEqual(
            url,
            'https://eu-central-2.console.aws.amazon.com/cloudwatch/home?region=eu-central-2'
            '#logsV2:log-groups/log-group/'
            '$252Faws$252Fecs$252Fjme-nivel-process-context-app-service/log-events/'
            'jme-nivel-process-context-app-service$252Fjme-nivel-process-context-app-service'
            '$252Fe7d0615da0574864a734b260147aed77')


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

    @patch('builtins.print')
    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_failed_rollout_aborts_immediately(self, mock_sleep, mock_boto_client, mock_print):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.describe_services.side_effect = _scripted_describe_services({
            'service-one': [_service_response('FAILED', 'arn:new-1', running=0, pending=0, failed=3)],
            'svc-2': [_service_response('IN_PROGRESS', 'arn:new-2', running=0, pending=1)],
        })
        mock_client.describe_task_definition.side_effect = _task_definition_side_effect(self.IMAGES)

        with self.assertRaises(DeploymentFailedError) as context:
            wait_until_deployments_completed('test-cluster', ['service-one', 'svc-2'], '0.0.2-new',
                                             'eu-central-2', interval=1, max_duration=600)

        error = context.exception
        self.assertEqual(
            str(error),
            'The deployment of image version 0.0.2-new failed: '
            'service-one (rollout FAILED (running 0/1, pending 0, failed 3))')
        self.assertEqual(error.expected_image_version, '0.0.2-new')
        self.assertEqual(list(error.failed_deployments), ['service-one'])
        self.assertEqual(error.failed_deployments['service-one'].task_definition_arn, 'arn:new-1')
        self.assertEqual(mock_client.describe_services.call_count, 2)
        mock_sleep.assert_not_called()

    @patch('builtins.print')
    @patch('boto3.client')
    @patch('time.sleep', return_value=None)
    def test_client_error_is_logged_and_next_poll_continues(self, mock_sleep, mock_boto_client, mock_print):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        client_error = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
            'DescribeServices')
        mock_client.describe_services.side_effect = [
            client_error,
            _service_response('COMPLETED', 'arn:new-1', running=1, pending=0),
        ]
        mock_client.describe_task_definition.side_effect = _task_definition_side_effect(self.IMAGES)

        result = wait_until_deployments_completed(
            'test-cluster', ['service-one'], '0.0.2-new', 'eu-central-2',
            interval=1, max_duration=1)

        self.assertEqual(result, {'service-one': 'arn:new-1'})
        lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any('ThrottlingException' in line and 'Rate exceeded' in line
                            for line in lines))
        mock_sleep.assert_called_once_with(1)


if __name__ == '__main__':
    unittest.main()
