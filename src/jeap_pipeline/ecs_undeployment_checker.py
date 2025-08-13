import boto3
import time
from botocore.exceptions import ClientError


def _is_service_undeployed(client, cluster_name: str, service_name: str) -> bool:
    """
    Checks whether the ECS service is undeployed, meaning it is either INACTIVE or missing.

    Args:
        client: The boto3 ECS client.
        cluster_name (str): The name of the ECS cluster.
        service_name (str): The name of the ECS service.

    Returns:
        bool: True if the service is undeployed, False otherwise.
    """
    try:
        response = client.describe_services(cluster=cluster_name, services=[service_name])
        services = response.get('services', [])
        failures = response.get('failures', [])

        if len(services) == 1:
            return services[0]['status'] == 'INACTIVE'
        elif len(services) == 0 and failures:
            return failures[0].get('reason') == 'MISSING'
        else:
            print(f"Unexpected response while checking undeployment status: {response}")
            return False
    except ClientError as e:
        print(f"AWS ClientError while checking service status: {e}")
        return False


def is_service_undeployed(cluster_name: str,
                               service_name: str,
                               aws_region: str,
                               verify_ssl: bool = True) -> bool:
    """
    Initializes the ECS client and checks if the service is undeployed.

    Args:
        cluster_name (str): The name of the ECS cluster.
        service_name (str): The name of the ECS service.
        aws_region (str): The AWS region.
        verify_ssl (bool): Whether to verify SSL certificates.

    Returns:
        bool: True if the service is undeployed, False otherwise.
    """
    client = boto3.client('ecs', region_name=aws_region, verify=verify_ssl)
    return _is_service_undeployed(client, cluster_name, service_name)

def wait_until_undeployment_has_finished(cluster_name: str,
                                         service_name: str,
                                         aws_region: str,
                                         interval: int = 20,
                                         max_duration: int = 480,
                                         verify_ssl: bool = True) -> None:
    """
    Waits until an ECS service is fully undeployed (i.e., its status is INACTIVE or it no longer exists).

    This function polls the ECS service status at regular intervals until the service is confirmed to be undeployed
    or the maximum wait time is reached.

    Args:
        cluster_name (str): The name of the ECS cluster.
        service_name (str): The name of the ECS service.
        aws_region (str): The AWS region where the ECS cluster is located.
        interval (int, optional): Time in seconds between status checks. Defaults to 20.
        max_duration (int, optional): Maximum time in seconds to wait for undeployment. Defaults to 480.
        verify_ssl (bool, optional): Whether to verify SSL certificates. Defaults to True.

    Raises:
        Exception: If the service is not undeployed within the maximum duration.
    """
    client = boto3.client('ecs', region_name=aws_region, verify=verify_ssl)
    call_count = 0
    max_calls = max_duration // interval

    print(f"Waiting for undeployment of service '{service_name}' in cluster '{cluster_name}'...")

    while call_count <= max_calls:
        if _is_service_undeployed(client, cluster_name, service_name):
            print(f"Undeployment of service '{service_name}' completed successfully.")
            return
        time.sleep(interval)
        call_count += 1

    raise Exception(f"Undeployment of service '{service_name}' did not complete within {max_duration // 60} minutes.")
