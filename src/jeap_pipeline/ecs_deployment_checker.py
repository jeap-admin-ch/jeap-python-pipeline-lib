import boto3
import time
from typing import Dict, Any

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
