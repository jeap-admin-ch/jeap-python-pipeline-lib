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
            contracts, as their absence cannot be distinguished from a failed contract publication. Requires
            jeap-message-contract-service 12.11.0 or later, which answers status 201 for an accepted declaration.

    Raises:
        requests.HTTPError: The Message Contract Service answered with an error status.
        RuntimeError: The declaration that the application version has no message contracts had no effect, either
            because the Message Contract Service does not support it yet or because it does not know the application
            name.
    """
    mcs_record_deployment_url = f"{mcs_url}/api/deployments/{app_name}/{app_version}/{environment}"
    params = {"noMessageContracts": "true"} if no_message_contracts else None

    headers = {
        "Content-Type": "application/json;charset=UTF-8"
    }

    print("Record deployment in Message Contract Service:")
    print(f"Request URL: {mcs_record_deployment_url}")
    if params:
        print(f"Request parameters: {params}")

    response = requests.put(mcs_record_deployment_url, headers=headers, params=params,
                            auth=HTTPBasicAuth(user, password))
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.text}")
    response.raise_for_status()

    if no_message_contracts and response.status_code != 201:
        raise RuntimeError(
            f"The Message Contract Service did not register the deployment of {app_name} {app_version} on "
            f"{environment} declared to have no message contracts (status {response.status_code}): "
            f"{response.text}. Check that the application name is correct and that the Message Contract Service "
            f"runs version 12.11.0 or later."
        )

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
