import boto3
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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


def _get_primary_deployment(client: boto3.client, cluster_name: str, service_name: str) -> Dict[str, Any]:
    response = client.describe_services(cluster=cluster_name, services=[service_name])
    deployments = response['services'][0]['deployments']
    return next((d for d in deployments if d['status'] == 'PRIMARY'), {})


def _get_task_definition(client: boto3.client, task_definition_arn: str) -> Dict[str, Any]:
    task_definition = client.describe_task_definition(taskDefinition=task_definition_arn)
    return task_definition['taskDefinition']


def _check_image_version(task_definition: Dict[str, Any], expected_image_version: str) -> bool:
    container_definitions = task_definition['containerDefinitions']
    image = container_definitions[0]['image']
    return image.endswith(expected_image_version)


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
    elif not image.endswith(expected_image_version):
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

    Make sure to set the following environment variables before running the script:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY

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
        Exception: If not all deployments complete within the maximum duration.
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
        for service_name in services:
            if service_name in completed:
                continue
            try:
                status = get_deployment_status(client, cluster_name, service_name,
                                               expected_image_version, image_cache)
            except client.exceptions.ClientError as e:
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


def _describe_deployment_state(client: boto3.client, primary_deployment: Dict[str, Any]) -> str:
    if not primary_deployment:
        return "no PRIMARY deployment found"
    state = primary_deployment.get('rolloutState', 'UNKNOWN')
    running = primary_deployment.get('runningCount', '?')
    desired = primary_deployment.get('desiredCount', '?')
    pending = primary_deployment.get('pendingCount', '?')
    failed = primary_deployment.get('failedTasks', '?')
    image = 'unknown'
    task_definition_arn = primary_deployment.get('taskDefinition')
    if task_definition_arn:
        try:
            image = _get_task_definition(client, task_definition_arn)['containerDefinitions'][0]['image']
        except Exception:
            pass  # progress logging must never break the wait loop
    return f"rollout {state} (running {running}/{desired}, pending {pending}, failed {failed}), current image {image}"


def wait_until_new_deployment_has_occurred(cluster_name: str,
                                           service_name: str,
                                           expected_image_version: str,
                                           aws_region: str,
                                           interval: int = 5,
                                           max_duration: int = 600,
                                           verify_ssl: bool = True,
                                           progress_interval: int = 30) -> str:
    """
    Waits until a new ECS deployment with the expected image version has completed.
    Make sure to set the following environment variables before running the script:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY

    Args:
        cluster_name (str): The name of the ECS cluster.
        service_name (str): The name of the ECS service.
        expected_image_version (str): The expected image version.
        aws_region (str): The AWS region.
        interval (int, optional): The interval in seconds between checks. Defaults to 5.
        max_duration (int, optional): The maximum duration in seconds to wait. Defaults to 600.
        verify_ssl (bool, optional): Whether to verify SSL certificates. Defaults to True.
        progress_interval (int, optional): The interval in seconds between progress log lines
            showing the current vs the expected deployment state. Defaults to 30.

    Returns:
        str: The ARN of the task definition if the deployment is successful.

    Raises:
        Exception: If the deployment does not complete within the maximum duration.
    """
    client = boto3.client('ecs', region_name=aws_region, verify=verify_ssl)
    call_count = 0
    max_calls = max_duration // interval
    log_every = max(1, progress_interval // interval)

    while call_count <= max_calls:
        try:
            primary_deployment = _get_primary_deployment(client, cluster_name, service_name)

            if primary_deployment and primary_deployment['rolloutState'] == 'COMPLETED':
                task_definition_arn = primary_deployment['taskDefinition']
                task_definition = _get_task_definition(client, task_definition_arn)

                if _check_image_version(task_definition, expected_image_version):
                    print(f"[{service_name}] Deployment completed with image version {expected_image_version}", flush=True)
                    return task_definition_arn

            if call_count % log_every == 0:
                print(f"[{service_name}] Waiting for deployment with expected image version "
                      f"{expected_image_version}: {_describe_deployment_state(client, primary_deployment)}", flush=True)
        except client.exceptions.ClientError as e:
            print(f"Error: {e}", flush=True)

        time.sleep(interval)
        call_count += 1

    raise Exception(f"The deployment of {service_name} with image version {expected_image_version} is not available "
                    f"after {max_duration // 60} minutes")
