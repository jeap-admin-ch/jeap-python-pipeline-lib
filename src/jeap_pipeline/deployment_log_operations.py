import json
import logging
from datetime import datetime

from requests import request
from requests.auth import HTTPBasicAuth


def put_deployment_state(url, deployment_id, deployment_state, username, password, message=None, properties=None):
    api_url = url + "/api/deployment/" + deployment_id + "/state"

    if message is not None:
        message = message.replace('\r', ' ')
        message = message.replace('\n', ' ')
        message = message.replace('"', '\'')

    json_obj = {
        "timestamp": __get_actual_timestamp(),
        "state": deployment_state,
        "message": message if message else '',
        "properties": properties if properties else {}
    }
    request_json = json.dumps(json_obj)
    print(f"@@@ api_url: {api_url}")
    print(f"@@@ request_json: {request_json}")

    return __request_deployment_log_service(api_url, "PUT", request_json, username, password)


def put_to_deployment_log_service(url, deployment_id, deployment_log_json, username, password,
                                  ready_for_deploy_check: bool = False):
    api_url = url + "/api/deployment/" + deployment_id + "?readyForDeployCheck=" + ready_for_deploy_check
    print(f"### api_url: {api_url}")

    return __request_deployment_log_service(api_url, "PUT", deployment_log_json, username, password)


def __request_deployment_log_service(url, method, json, username, password, fail_on_failure: bool = True):
    headers = {"Content-Type": "application/json"}
    auth = HTTPBasicAuth(username, password)
    response = request(method, url, json=json, auth=auth, headers=headers)
    if response.status_code >= 400:
        logging.error(f"Request failed with status code {response.status_code}: {response.text}")
        if fail_on_failure:
            response.raise_for_status()
    return response

def __get_actual_timestamp():
    actual_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return actual_timestamp
