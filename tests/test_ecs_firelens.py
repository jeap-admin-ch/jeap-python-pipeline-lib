from unittest.mock import MagicMock

import pytest

from src.jeap_pipeline.ecs_deployment_checker import _get_container_diagnostics


def collect(options, *, driver='awsfirelens', include_logs=True, logs=None):
    return _get_container_diagnostics(
        {'taskArn': 'arn:aws:ecs:eu-central-2:123:task/cluster/task-123',
         'containers': [{'name': 'app', 'logStreamName': 'awslogs-only-stream'}]},
        {'containerDefinitions': [{'name': 'app', 'logConfiguration': {
            'logDriver': driver, 'options': options}}]},
        'eu-central-2', include_logs, 100, True,
        {'eu-central-2': logs or MagicMock()})[0]


def options(**overrides):
    return {'Name': 'cloudwatch_logs', 'log_group_name': '/aws/ecs/service',
            'log_stream_prefix': 'service/app/', **overrides}


@pytest.mark.parametrize('prefix,expected', [
    ('service/app/', 'service/app/app-firelens-task-123'),
    ('custom-', 'custom-app-firelens-task-123'),
    ('', 'app-firelens-task-123'),
])
def test_firelens_reads_exact_stream_and_builds_link(prefix, expected):
    logs = MagicMock()
    logs.get_log_events.return_value = {'events': [{'message': 'startup failed'}]}
    result = collect(options(log_stream_prefix=prefix), logs=logs)
    assert result.has_cloudwatch_configuration
    assert not result.has_awslogs_configuration
    assert result.log_stream == expected
    assert result.log_events[0].message == 'startup failed'
    assert '/log-events/' + expected.replace('/', '$252F') in result.cloudwatch_log_url
    assert '$252Faws$252Fecs$252Fservice' in result.cloudwatch_log_url
    logs.get_log_events.assert_called_once_with(
        logGroupName='/aws/ecs/service', logStreamName=expected, limit=100, startFromHead=False)


def test_explicit_stream_name():
    result = collect({'Name': 'cloudwatch_logs', 'log_group_name': '/aws/ecs/service',
                      'log_stream_name': 'fixed'})
    assert result.log_stream == 'fixed'


@pytest.mark.parametrize('missing', ['log_group_name', 'log_stream_prefix'])
def test_incomplete_configuration_reports_error(missing):
    config = options()
    del config[missing]
    logs = MagicMock()
    result = collect(config, logs=logs)
    assert result.errors == ['CloudWatch log group or stream could not be determined']
    assert result.cloudwatch_log_url is None
    logs.get_log_events.assert_not_called()


def test_non_cloudwatch_firelens_is_skipped():
    logs = MagicMock()
    result = collect(options(Name='firehose'), logs=logs)
    assert not result.has_cloudwatch_configuration
    assert result.cloudwatch_log_url is None
    assert not result.errors
    logs.get_log_events.assert_not_called()


def test_log_access_failure_keeps_link():
    logs = MagicMock()
    logs.get_log_events.side_effect = PermissionError('AccessDenied')
    result = collect(options(), logs=logs)
    assert 'AccessDenied' in result.errors[0]
    assert result.cloudwatch_log_url


def test_no_log_fetch_unless_requested():
    logs = MagicMock()
    result = collect(options(), include_logs=False, logs=logs)
    assert result.cloudwatch_log_url
    assert not result.errors
    logs.get_log_events.assert_not_called()


def test_mixed_task_keeps_router_awslogs():
    logs = MagicMock()
    configs = [
        {'name': 'app', 'logConfiguration': {'logDriver': 'awsfirelens', 'options': options()}},
        {'name': 'firelens', 'logConfiguration': {'logDriver': 'awslogs', 'options': {
            'awslogs-group': '/aws/ecs/service', 'awslogs-stream-prefix': 'service/firelens'}}},
    ]
    result = _get_container_diagnostics(
        {'taskArn': 'arn:aws:ecs:eu-central-2:123:task/cluster/task-123',
         'containers': [{'name': 'app'}, {'name': 'firelens'}, {'name': 'injected'}]},
        {'containerDefinitions': configs}, 'eu-central-2', True, 100, True,
        {'eu-central-2': logs})
    assert [c.log_stream for c in result] == [
        'service/app/app-firelens-task-123', 'service/firelens/firelens/task-123', None]
    assert [c.has_awslogs_configuration for c in result] == [False, True, False]
    assert [c.has_cloudwatch_configuration for c in result] == [True, True, False]
    assert logs.get_log_events.call_count == 2
