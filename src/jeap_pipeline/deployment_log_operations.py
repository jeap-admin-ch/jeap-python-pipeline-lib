import json
import re
import subprocess
from uuid import uuid4
import requests
from datetime import datetime
from requests import request, Response
from requests.auth import HTTPBasicAuth

from .deployment_log_model import ChangeLog, DeploymentTarget, ComponentVersion, DeploymentUnit, Link, Deployment


def put_deployment_state(url: str,
                         deployment_id: str,
                         deployment_state: str,
                         username: str,
                         password: str,
                         message: str= None,
                         properties: dict= None):
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

def put_to_deployment_log_service(url: str,
                                  deployment_id: str,
                                  deployment_log_json: dict,
                                  username: str,
                                  password: str,
                                  ready_for_deploy_check: bool = False):
    """
    Update the deployment log service with new deployment data.

    Args:
        url (str): The base URL of the deployment service.
        deployment_id (str): The ID of the deployment to update.
        deployment_log_json (dict): The JSON data to update the deployment log with.
        username (str): The username for authentication.
        password (str): The password for authentication.
        ready_for_deploy_check (bool): readyForDeployCheck flag for the deployment log. Optional. Default: False

    Returns:
        Response: The response from the deployment log service.
    """
    api_url = f"{url}/api/deployment/{deployment_id}?readyForDeployCheck={str(ready_for_deploy_check).lower()}"
    print(f"### put_to_deployment_log_service: {api_url}")
    return __request_deployment_log_service(api_url, "PUT", deployment_log_json, username, password)

def get_previous_deployment_on_environment(url: str,
                                           system: str,
                                           component: str,
                                           environment: str,
                                           version_to_deploy: str,
                                           username: str,
                                           password: str):
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

def put_artifacts_version(url: str,
                          coordinates: str,
                          build_url: str,
                          username: str,
                          password: str):
    """
    Update the artifact version in the deployment log service.

    Args:
        url (str): The base URL of the deployment service.
        coordinates (str): The coordinates of the artifact.
        build_url (str): The URL of the build job.
        username (str): The username for authentication.
        password (str): The password for authentication.

    Returns:
        Response: The response from the deployment log service.
    """
    request_body: dict = {
        "coordinates": coordinates,
        "buildJobLink": build_url
    }

    print(f"### request_body: {request_body}")

    uuid = str(uuid4())
    api_url = url + "/api/artifact-version/" + uuid
    print(f"### api_url: {api_url}")
    return __request_deployment_log_service(api_url, "PUT", request_body, username, password)

def get_actual_timestamp() -> str:
    """
    Get the current timestamp in ISO 8601 format.

    Returns:
        str: The current timestamp.
    """
    actual_timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return actual_timestamp

def generate_deployment_id(component_name: str, env: str) -> str:
    """
    Generate a unique deployment ID.

    Args:
        component_name (str): The name of the component.
        env (str): The environment name.

    Returns:
        str: A unique deployment ID in the format 'component-env-timestamp'.
    """
    component = __escape_bit_component_name(component_name)
    timestamp = get_actual_timestamp()
    return f"{component}-{env}-{timestamp}"


def create_deployment_json(deployment_platform: str,
                           actual_timestamp: str,
                           system_name: str,
                           app_name: str,
                           cluster: str,
                           deploy_stage: str,
                           git_commit: str,
                           git_commit_timestamp: str,
                           version_control_url: str,
                           pipeline_run_url: str,
                           started_by: str,
                           image_tag: str,
                           git_tag_timestamp: str,
                           maven_published: str,
                           remedy_change_id: str,
                           deployment_target_url: str,
                           artifact_url: str,
                           deployment_log_url: str,
                           dl_username: str,
                           dl_password: str):
    """
    Create a JSON representation of a deployment.

    Args:
        deployment_platform (str): The deployment platform. E.g., 'AWS'.
        actual_timestamp (str): The timestamp when the deployment started.
        system_name (str): The name of the system.
        app_name (str): The name of the application.
        cluster (str): The name of the cluster.
        deploy_stage (str): The deployment stage.
        git_commit (str): The Git commit hash.
        git_commit_timestamp (str): The timestamp of the Git commit.
        version_control_url (str): The URL of the version control system.
        pipeline_run_url (str): The URL of the pipeline run.
        started_by (str): The user who started the deployment.
        image_tag (str): The image tag.
        git_tag_timestamp (str): The timestamp of the Git tag.
        maven_published (str): The Maven published version.
        remedy_change_id (str): The remedy change ID.
        deployment_target_url (str): The Deployment Target URL.
        artifact_url (str): The URL of the artifact.
        deployment_log_url (str): The URL of the deployment log service.
        dl_username (str): The username for the deployment log service.
        dl_password (str): The password for the deployment log service.

    Returns:
        dict: A dictionary representation of the deployment.
    """
    details: str = "cluster: " + cluster + ", service: " + app_name + ", tag: " + image_tag
    target = DeploymentTarget(deployment_platform, deployment_target_url, details).to_dict()

    # If the tag is not an annotated git tag that includes a timestamp, fall back to the commit timestamp
    git_tag_timestamp = git_commit_timestamp if not git_tag_timestamp else git_tag_timestamp
    print("### git_tag_timestamp: ", git_tag_timestamp)

    component_version = ComponentVersion(image_tag, git_tag_timestamp, version_control_url, git_commit,
                                         git_commit_timestamp, maven_published, app_name, system_name).to_dict()

    print("### component_version: ", component_version)
    unit = DeploymentUnit.docker_image(artifact_url).to_dict()

    #pipeline_run_url = get_github_action_job_url()
    print("## pipeline_run_url:", pipeline_run_url)
    link_pipeline_run_url = Link("Deployment Pipeline Run", pipeline_run_url)
    link_commit = Link("Commit", version_control_url)
    links = {link_pipeline_run_url, link_commit}

    changelog = create_change_log(actual_version=image_tag,
                                  actual_git_commit=git_commit,
                                  system_name=system_name,
                                  app_name=app_name,
                                  deploy_stage=deploy_stage,
                                  deployment_log_url=deployment_log_url,
                                  username=dl_username,
                                  password=dl_password)
    print("### changelog: ", changelog)

    deployment_create = Deployment(started_at=actual_timestamp,
                                   started_by=started_by,
                                   environment_name=deploy_stage,
                                   target=target,
                                   links=links,
                                   component_version=component_version,
                                   deployment_unit=unit,
                                   changelog=changelog,
                                   remedy_change_id=remedy_change_id,
                                   properties=None)
    return deployment_create.to_dict()

def create_change_log(actual_version: str,
                        actual_git_commit: str,
                        system_name: str,
                        app_name: str,
                        deploy_stage: str,
                        deployment_log_url: str,
                        username: str,
                        password: str) -> dict:
    """
    Create a change log for the deployment.

    Args:
        actual_version (str): The actual version being deployed.
        actual_git_commit (str): The actual Git commit hash.
        system_name (str): The name of the system.
        app_name (str): The name of the application.
        deploy_stage (str): The deployment stage.
        deployment_log_url (str): The URL of the deployment log service.
        username (str): The username for authentication.
        password (str): The password for authentication.

    Returns:
        dict: A dictionary representation of the change log.
    """

    previous_deployment = get_previous_deployment_on_environment(deployment_log_url, system_name, app_name, deploy_stage, actual_version, username, password)

    if previous_deployment is None:
        return {}

    previous_git_commit = previous_deployment['componentVersion']['commitRef']
    previous_version = previous_deployment['componentVersion']['versionName']
    print(f"### previous_git_commit: {previous_git_commit}")
    print("### previous_version: ",previous_version)
    print("### actual_version: ",actual_version)
    print("### actual_git_commit", actual_git_commit)

    # get git diffs
    git_log = subprocess.run(
        ["git", "log", "--max-count=255", "--oneline", f"{previous_git_commit}..{actual_git_commit}"], capture_output=True, text=True
    )
    print(f"git_log: {git_log}")
    issues_pattern = r'[A-Z][A-Z0-9]+\-[0-9]+'
    issues_set = set(re.findall(issues_pattern, git_log.stdout))
    sorted_issues_set = sorted(issues_set)
    print(f"sorted_issues_set: {sorted_issues_set}")

    return ChangeLog(version_name=actual_version,
                     current_version_on_environment=previous_version,
                     changelog_jira_issue_keys=sorted_issues_set).to_dict()

def get_commit_details(commit_sha: str) -> tuple:
    """
    Get the details of a specific commit.

    Args:
        commit_sha (str): The SHA of the commit.

    Returns:
        tuple: A tuple containing the commit timestamp and committer name.
    """
    result = subprocess.run(['git', 'show', '-s', '--format=%cI|%cn', commit_sha], capture_output=True, text=True, check=True)
    commit_timestamp, committer_name = result.stdout.strip().split('|')
    return commit_timestamp, committer_name

def get_tagged_at(version_name: str) -> str:
    """
    Get the timestamp when a specific version was tagged.

    Args:
        version_name (str): The name of the version.

    Returns:
        str: The timestamp of the tag.
    """
    result = subprocess.run(['git', 'for-each-ref', '--format=%(taggerdate:iso-strict)', f'refs/tags/v{version_name}'], capture_output=True, text=True, check=True)
    return result.stdout.strip()

def __escape_bit_component_name(component: str) -> str:
    """
    Escape the 'bit/' prefix from the component name.

    Args:
        component (str): The component name.

    Returns:
        str: The escaped component name.
    """
    return component.replace('bit/', '')


def __request_deployment_log_service(url: str,
                                     method: str,
                                     request_body: dict,
                                     username: str,
                                     password: str,
                                     fail_on_failure: bool = True) -> Response:
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

