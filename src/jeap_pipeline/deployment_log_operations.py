import json
from uuid import uuid4

import requests
from datetime import datetime
from requests import request
from requests.auth import HTTPBasicAuth

def put_deployment_state(url, deployment_id, deployment_state, username, password, message=None, properties=None):
    """
    Update the state of a deployment.

    Args:
        url (str): The base URL of the deployment service.
        deployment_id (str): The ID of the deployment to update.
        deployment_state (str): The new state of the deployment.
        username (str): The username for authentication.
        password (str): The password for authentication.
        message (str, optional): An optional message describing the state change.
        properties (dict, optional): Additional properties related to the deployment state.

    Returns:
        Response: The response from the deployment log service.
    """
    api_url = f"{url}/api/deployment/{deployment_id}/state"

    if message:
        message = str(message).replace('\r', ' ').replace('\n', ' ').replace('"', "'")

    request_json = {
        "timestamp": get_actual_timestamp(),
        "state": deployment_state,
        "message": message if message else '',
        "properties": properties if properties else {}
    }

    return __request_deployment_log_service(api_url, "PUT", request_json, username, password)

def put_to_deployment_log_service(url, deployment_id, deployment_log_json, username, password):
    """
    Update the deployment log service with new deployment data.

    Args:
        url (str): The base URL of the deployment service.
        deployment_id (str): The ID of the deployment to update.
        deployment_log_json (dict): The JSON data to update the deployment log with.
        username (str): The username for authentication.
        password (str): The password for authentication.

    Returns:
        Response: The response from the deployment log service.
    """
    api_url = f"{url}/api/deployment/{deployment_id}?readyForDeployCheck=false"
    print(f"### put_to_deployment_log_service: {api_url}")
    return __request_deployment_log_service(api_url, "PUT", deployment_log_json, username, password)

def get_previous_deployment_on_environment(url, system, component, environment, version_to_deploy, username, password):
    """
    Retrieve the previous deployment on a specific environment.

    Args:
        url (str): The base URL of the deployment service.
        system (str): The system name.
        component (str): The component name.
        environment (str): The environment name.
        version_to_deploy (str): The version to deploy.
        username (str): The username for authentication.
        password (str): The password for authentication.

    Returns:
        dict or None: The JSON data of the previous deployment if found, otherwise None.
    """
    environment = environment.upper()
    api_url = f"{url}/api/system/{system}/component/{component}/previousDeployment/{environment}?version={version_to_deploy}"
    print(f"### get_previous_deployment_on_environment: {api_url}")

    response = __request_deployment_log_service(api_url, "GET", None, username, password, False)

    if response.status_code == 404:
        print("Previous deployment not found")
        return None
    else:
        try:
            response.raise_for_status()  # Raise an exception for 4xx or 5xx errors
        except requests.exceptions.RequestException as e:
            print(f"get_previous_deployment_on_environment failed: {e}")
            return None

    response_json_data = json.loads(response.text)
    return response_json_data

def put_artifacts_version(url, coordinates, build_url, username, password):

    request_body = {
        "coordinates": coordinates,
        "buildJobLink": build_url
    }

    print(f"### request_body: {request_body}")

    uuid = str(uuid4())
    api_url = url + "/api/artifact-version/" + uuid
    print(f"### api_url: {api_url}")
    return __request_deployment_log_service(api_url, "PUT", request_body, username, password)


def get_actual_timestamp():
    """
    Get the current timestamp in ISO 8601 format.

    Returns:
        str: The current timestamp.
    """
    actual_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return actual_timestamp

def __request_deployment_log_service(url, method, request_body, username, password, fail_on_failure: bool = True):
    """
    Make a request to the deployment log service.

    Args:
        url (str): The URL of the deployment log service.
        method (str): The HTTP method to use (e.g., 'GET', 'POST', 'PUT').
        request_body (dict): The JSON data to send in the request body.
        username (str): The username for authentication.
        password (str): The password for authentication.
        fail_on_failure (bool, optional): Whether to raise an exception on failure. Defaults to True.

    Returns:
        Response: The response from the deployment log service.
    """
    headers = {"Content-Type": "application/json"}
    auth = HTTPBasicAuth(username, password)
    response = request(method, url, json=request_body, auth=auth, headers=headers)
    if response.status_code >= 400:
        print(f"Request failed with status code {response.status_code}: {response.text}")
        if fail_on_failure:
            response.raise_for_status()
    return response

