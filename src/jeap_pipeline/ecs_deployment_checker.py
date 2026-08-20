import boto3
import time
from botocore.exceptions import ClientError
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

# Deployment states derived from the PRIMARY ECS deployment compared against the expected image version
WAITING_FOR_ROLLOUT = 'WAITING_FOR_ROLLOUT'
ROLLOUT_IN_PROGRESS = 'ROLLOUT_IN_PROGRESS'
ROLLOUT_COMPLETED = 'ROLLOUT_COMPLETED'
ROLLOUT_FAILED = 'ROLLOUT_FAILED'
STATE_UNKNOWN = 'UNKNOWN'

_STATE_LABELS = {
    WAITING_FOR_ROLLOUT: 'waiting for rollout',
    ROLLOUT_IN_PROGRESS: 'rollout in progress',
    ROLLOUT_FAILED: 'rollout failed',
    STATE_UNKNOWN: 'state unknown',
}


@dataclass
class DeploymentStatus:
    state: str
    running: Any = '?'
    desired: Any = '?'
    pending: Any = '?'
    failed_tasks: Any = '?'
    current_image_tag: str = 'unknown'
    task_definition_arn: Optional[str] = None


@dataclass
class CloudWatchLogEvent:
    message: str
    timestamp: Optional[int] = None
    ingestion_time: Optional[int] = None


@dataclass
class ContainerFailureDiagnostics:
    name: str
    exit_code: Optional[int] = None
    reason: Optional[str] = None
    last_status: Optional[str] = None
    has_awslogs_configuration: bool = False
    log_group: Optional[str] = None
    log_stream: Optional[str] = None
    log_region: Optional[str] = None
    cloudwatch_log_url: Optional[str] = None
    log_events: List[CloudWatchLogEvent] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class StoppedTaskDiagnostics:
    task_arn: str
    task_definition_arn: str
    stopped_at: Optional[datetime] = None
    stop_code: Optional[str] = None
    stopped_reason: Optional[str] = None
    containers: List[ContainerFailureDiagnostics] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class ServiceFailureDiagnostics:
    service_name: str
    deployment_status: Optional[DeploymentStatus] = None
    stopped_task: Optional[StoppedTaskDiagnostics] = None
    errors: List[str] = field(default_factory=list)


@dataclass
class DeploymentFailureDiagnostics:
    services: List[ServiceFailureDiagnostics] = field(default_factory=list)


def _get_primary_deployment(client: boto3.client, cluster_name: str, service_name: str) -> Dict[str, Any]:
    response = client.describe_services(cluster=cluster_name, services=[service_name])
    deployments = response['services'][0]['deployments']
    return next((d for d in deployments if d['status'] == 'PRIMARY'), {})


def _get_task_definition(client: boto3.client, task_definition_arn: str) -> Dict[str, Any]:
    task_definition = client.describe_task_definition(taskDefinition=task_definition_arn)
    return task_definition['taskDefinition']


def _get_image(client: boto3.client, task_definition_arn: Optional[str],
               image_cache: Optional[Dict[str, str]]) -> str:
    if not task_definition_arn:
        return 'unknown'
    if image_cache is not None and task_definition_arn in image_cache:
        return image_cache[task_definition_arn]
    try:
        image = _get_task_definition(client, task_definition_arn)['containerDefinitions'][0]['image']
    except Exception:
        return 'unknown'  # status lookup must never break the wait loop; do not cache failures
    if image_cache is not None:
        image_cache[task_definition_arn] = image
    return image


def get_deployment_status(client: boto3.client,
                          cluster_name: str,
                          service_name: str,
                          expected_image_version: str,
                          image_cache: Optional[Dict[str, str]] = None) -> DeploymentStatus:
    """
    Determines the deployment state of an ECS service relative to an expected image version.

    The PRIMARY deployment's image is compared against the expected version first: as long as the
    PRIMARY deployment still runs a different image, the state is WAITING_FOR_ROLLOUT regardless of
    its rollout state (the previous deployment's rollout is naturally COMPLETED). Only once the
    PRIMARY deployment references the expected image does the ECS rollout state decide between
    ROLLOUT_IN_PROGRESS, ROLLOUT_COMPLETED and ROLLOUT_FAILED.

    Args:
        client (boto3.client): The ECS client.
        cluster_name (str): The name of the ECS cluster.
        service_name (str): The name of the ECS service.
        expected_image_version (str): The expected image version.
        image_cache (dict, optional): Cache mapping task definition ARNs to images. Task definitions
            are immutable, so passing the same dict across polls avoids repeated API lookups.

    Returns:
        DeploymentStatus: The derived state plus task counts, current image tag and task definition ARN.
    """
    primary_deployment = _get_primary_deployment(client, cluster_name, service_name)
    if not primary_deployment:
        return DeploymentStatus(state=STATE_UNKNOWN)

    task_definition_arn = primary_deployment.get('taskDefinition')
    image = _get_image(client, task_definition_arn, image_cache)
    image_tag = image.rsplit(':', 1)[-1] if image != 'unknown' else 'unknown'

    if image == 'unknown':
        state = STATE_UNKNOWN
    elif image_tag != expected_image_version:
        state = WAITING_FOR_ROLLOUT
    else:
        rollout_state = primary_deployment.get('rolloutState', 'UNKNOWN')
        state = {'COMPLETED': ROLLOUT_COMPLETED, 'FAILED': ROLLOUT_FAILED}.get(rollout_state, ROLLOUT_IN_PROGRESS)

    return DeploymentStatus(state=state,
                            running=primary_deployment.get('runningCount', '?'),
                            desired=primary_deployment.get('desiredCount', '?'),
                            pending=primary_deployment.get('pendingCount', '?'),
                            failed_tasks=primary_deployment.get('failedTasks', '?'),
                            current_image_tag=image_tag,
                            task_definition_arn=task_definition_arn)


def _describe_stopped_tasks(client: boto3.client,
                            cluster_name: str,
                            service_name: str,
                            errors: List[str]) -> List[Dict[str, Any]]:
    task_arns = []
    request = {
        'cluster': cluster_name,
        'serviceName': service_name,
        'desiredStatus': 'STOPPED',
    }
    while True:
        try:
            response = client.list_tasks(**request)
        except Exception as e:
            errors.append(f"Could not list stopped ECS tasks: {e}")
            break
        task_arns.extend(response.get('taskArns', []))
        next_token = response.get('nextToken')
        if not next_token:
            break
        request['nextToken'] = next_token

    tasks = []
    for offset in range(0, len(task_arns), 100):
        try:
            response = client.describe_tasks(cluster=cluster_name, tasks=task_arns[offset:offset + 100])
            tasks.extend(response.get('tasks', []))
            for failure in response.get('failures', []):
                errors.append(f"Could not describe ECS task {failure.get('arn', 'unknown')}: "
                              f"{failure.get('reason', 'unknown reason')}")
        except Exception as e:
            errors.append(f"Could not describe stopped ECS tasks: {e}")
    return tasks


def _stopped_at_sort_key(task: Dict[str, Any]) -> float:
    stopped_at = task.get('stoppedAt')
    if hasattr(stopped_at, 'timestamp'):
        return stopped_at.timestamp()
    if isinstance(stopped_at, (int, float)):
        return float(stopped_at)
    return float('-inf')


def _get_last_stopped_task(client: boto3.client,
                           cluster_name: str,
                           service_name: str,
                           task_definition_arn: str,
                           errors: List[str]) -> Optional[Dict[str, Any]]:
    tasks = _describe_stopped_tasks(client, cluster_name, service_name, errors)
    matching_tasks = [task for task in tasks
                      if task.get('taskDefinitionArn') == task_definition_arn]
    return max(matching_tasks, key=_stopped_at_sort_key) if matching_tasks else None


def _log_configuration_by_container(task_definition: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    result = {}
    for container_definition in task_definition.get('containerDefinitions', []):
        log_configuration = container_definition.get('logConfiguration', {})
        if log_configuration.get('logDriver') == 'awslogs':
            result[container_definition.get('name', '')] = log_configuration.get('options') or {}
    return result


def _task_id(task_arn: str) -> str:
    return task_arn.rsplit('/', 1)[-1]


def _encode_cloudwatch_path(value: str) -> str:
    return quote(quote(value, safe=''), safe='').replace('%', '$')


def build_cloudwatch_log_stream_url(
        aws_region: str,
        log_group: str,
        log_stream: str) -> str:
    """Build a CloudWatch console URL pointing directly to a log stream."""
    encoded_group = _encode_cloudwatch_path(log_group)
    encoded_stream = _encode_cloudwatch_path(log_stream)

    return (
        f"https://{aws_region}.console.aws.amazon.com/cloudwatch/home"
        f"?region={aws_region}"
        f"#logsV2:log-groups/log-group/{encoded_group}"
        f"/log-events/{encoded_stream}"
    )


def _get_log_events(logs_clients: Dict[str, Any],
                    aws_region: str,
                    verify_ssl: bool,
                    log_group: str,
                    log_stream: str,
                    limit: int,
                    errors: List[str]) -> List[CloudWatchLogEvent]:
    try:
        if aws_region not in logs_clients:
            logs_clients[aws_region] = boto3.client('logs', region_name=aws_region, verify=verify_ssl)
        response = logs_clients[aws_region].get_log_events(logGroupName=log_group,
                                                           logStreamName=log_stream,
                                                           limit=limit,
                                                           startFromHead=False)
        return [CloudWatchLogEvent(message=event.get('message', ''),
                                   timestamp=event.get('timestamp'),
                                   ingestion_time=event.get('ingestionTime'))
                for event in response.get('events', [])]
    except Exception as e:
        errors.append(f"Could not load CloudWatch log events: {e}")
        return []


def _get_container_diagnostics(task: Dict[str, Any],
                               task_definition: Dict[str, Any],
                               default_aws_region: str,
                               include_logs: bool,
                               log_event_limit: int,
                               verify_ssl: bool,
                               logs_clients: Dict[str, Any]) -> List[ContainerFailureDiagnostics]:
    log_configurations = _log_configuration_by_container(task_definition)
    containers = []
    for container in task.get('containers', []):
        name = container.get('name', 'unknown')
        has_awslogs_configuration = name in log_configurations
        log_options = log_configurations.get(name, {})
        log_group = log_options.get('awslogs-group')
        log_region = (log_options.get('awslogs-region', default_aws_region)
                      if has_awslogs_configuration else None)
        log_stream = container.get('logStreamName') if has_awslogs_configuration else None
        stream_prefix = log_options.get('awslogs-stream-prefix')
        if not log_stream and stream_prefix and name:
            log_stream = f"{stream_prefix}/{name}/{_task_id(task.get('taskArn', ''))}"

        cloudwatch_log_url = (
            build_cloudwatch_log_stream_url(log_region, log_group, log_stream)
            if log_region and log_group and log_stream
            else None
        )

        diagnostics = ContainerFailureDiagnostics(name=name,
                                                  exit_code=container.get('exitCode'),
                                                  reason=container.get('reason'),
                                                  last_status=container.get('lastStatus'),
                                                  has_awslogs_configuration=has_awslogs_configuration,
                                                  log_group=log_group,
                                                  log_stream=log_stream,
                                                  log_region=log_region,
                                                  cloudwatch_log_url=cloudwatch_log_url)
        if include_logs and has_awslogs_configuration:
            if not log_group or not log_stream or not log_region:
                diagnostics.errors.append("CloudWatch log group or stream could not be determined")
            else:
                diagnostics.log_events = _get_log_events(logs_clients, log_region, verify_ssl,
                                                          log_group, log_stream, log_event_limit,
                                                          diagnostics.errors)
        containers.append(diagnostics)
    return containers


def get_failure_diagnostics(cluster_name: str,
                            services: List[str],
                            expected_image_version: str,
                            aws_region: str,
                            deployment_statuses: Optional[Dict[str, DeploymentStatus]] = None,
                            include_logs: bool = False,
                            log_event_limit: int = 100,
                            verify_ssl: bool = True) -> DeploymentFailureDiagnostics:
    """Collect structured ECS deployment failure details without producing output.

    Each AWS lookup is isolated: unavailable stopped-task details, task definitions or CloudWatch
    logs are recorded in the corresponding ``errors`` list without discarding information obtained
    by the other lookups. Status snapshots can be supplied to preserve a failed task definition if
    ECS has already rolled back. Application logs are loaded only when ``include_logs`` is explicitly
    true.
    """
    if not 1 <= log_event_limit <= 10_000:
        raise ValueError("log_event_limit must be between 1 and 10000")

    client = boto3.client('ecs', region_name=aws_region, verify=verify_ssl)
    image_cache: Dict[str, str] = {}
    logs_clients: Dict[str, Any] = {}
    result = DeploymentFailureDiagnostics()

    for service_name in services:
        service = ServiceFailureDiagnostics(service_name=service_name)
        result.services.append(service)
        status = deployment_statuses.get(service_name) if deployment_statuses else None
        if status is None:
            try:
                status = get_deployment_status(client, cluster_name, service_name,
                                               expected_image_version, image_cache)
            except Exception as e:
                service.errors.append(f"Could not determine ECS deployment status: {e}")
                continue
        service.deployment_status = status
        if status.state == WAITING_FOR_ROLLOUT:
            service.errors.append(
                f"Rollout of expected image {expected_image_version} did not become PRIMARY; "
                "stopped-task diagnostics were skipped")
            continue
        if status.state == STATE_UNKNOWN:
            service.errors.append(
                "Deployment state is unknown; stopped-task diagnostics were skipped")
            continue
        if status.state == ROLLOUT_COMPLETED:
            continue

        task_definition_arn = status.task_definition_arn
        if not task_definition_arn:
            service.errors.append("ECS PRIMARY deployment has no task definition")
            continue

        error_count_before_lookup = len(service.errors)
        stopped_task = _get_last_stopped_task(client, cluster_name, service_name,
                                              task_definition_arn, service.errors)
        if not stopped_task:
            if len(service.errors) == error_count_before_lookup:
                service.errors.append("No stopped ECS task found for the deployment task definition")
            continue

        task_diagnostics = StoppedTaskDiagnostics(
            task_arn=stopped_task.get('taskArn', ''),
            task_definition_arn=task_definition_arn,
            stopped_at=stopped_task.get('stoppedAt'),
            stop_code=stopped_task.get('stopCode'),
            stopped_reason=stopped_task.get('stoppedReason'))
        service.stopped_task = task_diagnostics

        try:
            task_definition = _get_task_definition(client, task_definition_arn)
        except Exception as e:
            task_diagnostics.errors.append(f"Could not describe ECS task definition: {e}")
            task_definition = {}

        task_diagnostics.containers = _get_container_diagnostics(
            stopped_task, task_definition, aws_region, include_logs, log_event_limit,
            verify_ssl, logs_clients)
        if not task_diagnostics.containers:
            task_diagnostics.errors.append("Stopped ECS task has no container details")

    return result


def _format_clock(seconds: int) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"


def _format_duration(seconds: int) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}m{secs:02d}s"


def _describe_status(status: DeploymentStatus, rollout_already_started: bool) -> str:
    if status.state == WAITING_FOR_ROLLOUT:
        return f"waiting for rollout (still on {status.current_image_tag})"
    counts = f"running {status.running}/{status.desired}, pending {status.pending}"
    if status.state == ROLLOUT_IN_PROGRESS:
        return f"rollout {'in progress' if rollout_already_started else 'started'} ({counts})"
    if status.state == ROLLOUT_FAILED:
        return f"rollout FAILED ({counts}, failed {status.failed_tasks})"
    return "deployment state unknown (no PRIMARY deployment or task definition unavailable)"


class DeploymentFailedError(Exception):
    def __init__(self,
                 expected_image_version: str,
                 failed_deployments: Dict[str, DeploymentStatus]):
        self.expected_image_version = expected_image_version
        self.failed_deployments = dict(failed_deployments)
        details = ", ".join(
            f"{service_name} ({_describe_status(status, True)})"
            for service_name, status in self.failed_deployments.items())
        super().__init__(
            f"The deployment of image version {expected_image_version} failed: {details}")


def _summarize_pending(statuses: Dict[str, DeploymentStatus], pending_services: List[str]) -> str:
    states = [statuses[s].state if s in statuses else STATE_UNKNOWN for s in pending_services]
    plural = 's' if len(pending_services) != 1 else ''
    if all(state == WAITING_FOR_ROLLOUT for state in states):
        return f"still waiting for rollout: {len(pending_services)} service{plural}"
    counts = ", ".join(f"{states.count(state)} {label}"
                       for state, label in _STATE_LABELS.items() if state in states)
    return f"still waiting: {counts}"


def wait_until_deployments_completed(cluster_name: str,
                                     services: List[str],
                                     expected_image_version: str,
                                     aws_region: str,
                                     interval: int = 5,
                                     max_duration: int = 600,
                                     verify_ssl: bool = True,
                                     heartbeat_interval: int = 300) -> Dict[str, str]:
    """
    Waits until the ECS deployments of all given services have completed with the expected image version.

    All services are polled in a single loop, so the log stays concise: one aligned line per service
    state change (waiting for rollout -> rollout started -> rollout in progress -> rollout completed),
    prefixed with the elapsed time, plus a single-line heartbeat while nothing changes.

    AWS credentials are resolved through the boto3 default credential provider chain, for example
    environment variables, a shared credentials file, container credentials or an IAM role.

    Args:
        cluster_name (str): The name of the ECS cluster.
        services (list): The names of the ECS services.
        expected_image_version (str): The expected image version.
        aws_region (str): The AWS region.
        interval (int, optional): The interval in seconds between checks. Defaults to 5.
        max_duration (int, optional): The maximum duration in seconds to wait. Defaults to 600.
        verify_ssl (bool, optional): Whether to verify SSL certificates. Defaults to True.
        heartbeat_interval (int, optional): Seconds without any state change after which a one-line
            heartbeat is logged. Defaults to 300.

    Returns:
        dict: Mapping of service name to the ARN of the deployed task definition.

    Raises:
        DeploymentFailedError: If ECS reports a failed rollout.
        Exception: If the deployment does not complete within the maximum duration.
    """
    client = boto3.client('ecs', region_name=aws_region, verify=verify_ssl)
    name_width = max(len(service_name) for service_name in services)
    image_cache: Dict[str, str] = {}
    completed: Dict[str, str] = {}
    statuses: Dict[str, DeploymentStatus] = {}
    last_logged: Dict[str, tuple] = {}
    rollout_started: Dict[str, bool] = {}
    last_log_elapsed = 0
    call_count = 0
    max_calls = max_duration // interval

    print(f"Waiting for image {expected_image_version} on cluster {cluster_name} "
          f"(timeout {_format_duration(max_duration)})", flush=True)

    while call_count <= max_calls:
        elapsed = call_count * interval
        anything_logged = False
        failed_services = []
        for service_name in services:
            if service_name in completed:
                continue
            try:
                status = get_deployment_status(client, cluster_name, service_name,
                                               expected_image_version, image_cache)
            except ClientError as e:
                print(f"Error: {e}", flush=True)
                continue
            statuses[service_name] = status
            if status.state == ROLLOUT_COMPLETED:
                completed[service_name] = status.task_definition_arn
                print(f"[{_format_clock(elapsed)}] {service_name:<{name_width}}  "
                      f"rollout completed after {_format_duration(elapsed)}", flush=True)
                anything_logged = True
                continue
            logged_key = (status.state, status.running, status.pending)
            if logged_key != last_logged.get(service_name):
                print(f"[{_format_clock(elapsed)}] {service_name:<{name_width}}  "
                      f"{_describe_status(status, rollout_started.get(service_name, False))}", flush=True)
                last_logged[service_name] = logged_key
                anything_logged = True
            if status.state == ROLLOUT_IN_PROGRESS:
                rollout_started[service_name] = True
            elif status.state == ROLLOUT_FAILED:
                failed_services.append(service_name)

        if failed_services:
            raise DeploymentFailedError(
                expected_image_version,
                {service_name: statuses[service_name] for service_name in failed_services})

        if len(completed) == len(services):
            plural = 's' if len(services) != 1 else ''
            print(f"All {len(services)} service{plural} deployed {expected_image_version}", flush=True)
            return completed

        if anything_logged:
            last_log_elapsed = elapsed
        elif elapsed - last_log_elapsed >= heartbeat_interval:
            pending_services = [s for s in services if s not in completed]
            print(f"[{_format_clock(elapsed)}] {_summarize_pending(statuses, pending_services)}", flush=True)
            last_log_elapsed = elapsed

        time.sleep(interval)
        call_count += 1

    pending_services = [s for s in services if s not in completed]
    details = ", ".join(f"{s} ({_describe_status(statuses[s], True)})" if s in statuses else s
                        for s in pending_services)
    raise Exception(f"The deployment of image version {expected_image_version} did not complete within "
                    f"{_format_duration(max_duration)}. Incomplete services: {details}")
