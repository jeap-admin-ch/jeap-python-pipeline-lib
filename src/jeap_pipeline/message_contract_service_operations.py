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

def record_deployment(mcs_url: str, user: str, password: str, app_name: str, app_version: str, environment: str):
    mcs_record_deployment_url = f"{mcs_url}/api/deployments/{app_name}/{app_version}/{environment}"

    headers = {
        "Content-Type": "application/json;charset=UTF-8"
    }

    print("Record deployment in Message Contract Service:")
    print(f"Request URL: {mcs_record_deployment_url}")

    response = requests.put(mcs_record_deployment_url, headers=headers, auth=HTTPBasicAuth(user, password))
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.text}")
    response.raise_for_status()
