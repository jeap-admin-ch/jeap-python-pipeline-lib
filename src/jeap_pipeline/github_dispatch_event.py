import os
import requests
import json
from typing import Optional, List


def send_dispatch_event(organization: str, repository_name: str, stage: str, version: str, services: List[str]) -> None:
    """
    Sends a GitHub Repository Dispatch Event to trigger workflows.

    Make sure to set the following environment variable before running the script:
    - GITHUB_TOKEN

    Args:
        organization (str): The name of the GitHub organization.
        repository_name (str): The name of the GitHub repository.
        stage (str): The deployment stage (e.g., dev, staging, prod).
        version (str): The version of the deployment.
        services List[str]: A comma-separated list of services.

    Returns:
        None

    Raises:
        requests.exceptions.RequestException: If the request to the GitHub API fails.
    """
    github_token: Optional[str] = os.getenv('GITHUB_TOKEN')

    if not github_token:
        raise EnvironmentError("GITHUB_TOKEN environment variable is not set")

    payload = {
        "event_type": "new-version-published",
        "client_payload": {
            "stage": stage,
            "services": services,
            "version": version
        }
    }

    repository_dispatch_url = f"https://api.github.com/repos/{organization}/{repository_name}/dispatches"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    print("Send dispatch event:")
    print(f"Request URL: {repository_dispatch_url}")
    print(f"Request Payload: {json.dumps(payload, indent=2)}")

    response = requests.post(repository_dispatch_url, headers=headers, data=json.dumps(payload))
    response.raise_for_status()

    print("Dispatch event sent successfully")
