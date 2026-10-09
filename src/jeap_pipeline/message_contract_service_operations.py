import requests
from requests.auth import HTTPBasicAuth


class CompatibilityResult:
    def __init__(self, compatible: bool, message: str):
        self.compatible = compatible
        self.message = message

def get_compatibility(mcs_url: str, user: str, password: str, app_name: str, app_version: str, environment: str) -> CompatibilityResult:
    mcs_check_compatibility_url = f"{mcs_url}/api/deployments/compatibility/{app_name}/{app_version}/{environment}"

    headers = {
        "Accept": "application/json"
    }

    print("Get compatibility from Message Contract Service:")
    print(f"Request URL: {mcs_check_compatibility_url}")

    response = requests.get(mcs_check_compatibility_url, headers=headers, auth=HTTPBasicAuth(user, password))
    print(f"Response Status: {response.status_code}")
    print(f"Response Body: {response.text}")
    response.raise_for_status()

    response_data = response.json()
    return CompatibilityResult(compatible=response_data['compatible'], message=response_data['message'])

def record_deployment(mcs_url: str, user: str, password: str, app_name: str, app_version: str, environment: str,
                      no_message_contracts: bool = False):
    """
    Record the deployment of an application version on an environment in the Message Contract Service.

    Args:
        mcs_url (str): The Message Contract Service URL, without a trailing slash.
        user (str): The user for the Message Contract Service.
        password (str): The password for the Message Contract Service.
        app_name (str): The application name used for message contracts.
        app_version (str): The deployed application version.
        environment (str): The environment the application version has been deployed on.
        no_message_contracts (bool): Declares that the deployed application version has no message contracts. Without
            this declaration, the Message Contract Service ignores the deployment of an application version without
            contracts, as their absence cannot be distinguished from a failed contract publication.
    """
    mcs_record_deployment_url = f"{mcs_url}/api/deployments/{app_name}/{app_version}/{environment}"
    if no_message_contracts:
        mcs_record_deployment_url += "?noMessageContracts=true"

    headers = {
        "Content-Type": "application/json;charset=UTF-8"
    }

    print("Record deployment in Message Contract Service:")
    print(f"Request URL: {mcs_record_deployment_url}")

    response = requests.put(mcs_record_deployment_url, headers=headers, auth=HTTPBasicAuth(user, password))
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.text}")
    response.raise_for_status()

def delete_deployments(mcs_url: str, user: str, password: str, app_name: str, environment: str):
    mcs_delete_deployment_url = f"{mcs_url}/api/deployments/{app_name}/{environment}"

    headers = {
        "Accept": "application/json"
    }

    print("Delete deployment from Message Contract Service:")
    print(f"Request URL: {mcs_delete_deployment_url}")

    response = requests.delete(mcs_delete_deployment_url, headers=headers, auth=HTTPBasicAuth(user, password))
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.text}")
    response.raise_for_status()
