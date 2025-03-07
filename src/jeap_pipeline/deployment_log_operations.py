import json
import requests
from datetime import datetime
from requests import request
from requests.auth import HTTPBasicAuth

def put_deployment_state(url, deployment_id, deployment_state, username, password, message=None, properties=None):
    api_url = f"{url}/api/deployment/{deployment_id}/state"

    if message:
        message = str(message).replace('\r', ' ').replace('\n', ' ').replace('"', "'")

    request_json = {
        "timestamp": __get_actual_timestamp(),
        "state": deployment_state,
        "message": message if message else '',
        "properties": properties if properties else {}
    }

    return __request_deployment_log_service(api_url, "PUT", request_json, username, password)

def put_to_deployment_log_service(url, deployment_id, deployment_log_json, username, password):
    api_url = f"{url}/api/deployment/{deployment_id}?readyForDeployCheck=false"
    print(f"### put_to_deployment_log_service: {api_url}")
    return __request_deployment_log_service(api_url, "PUT", deployment_log_json, username, password)

def get_previous_deployment_on_environment(url, system, component, environment, version_to_deploy, username, password):
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

def __request_deployment_log_service(url, method, request_body, username, password, fail_on_failure: bool = True):
    headers = {"Content-Type": "application/json"}
    auth = HTTPBasicAuth(username, password)
    response = request(method, url, json=request_body, auth=auth, headers=headers)
    if response.status_code >= 400:
        print(f"Request failed with status code {response.status_code}: {response.text}")
        if fail_on_failure:
            response.raise_for_status()
    return response

def __get_actual_timestamp():
    actual_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return actual_timestamp