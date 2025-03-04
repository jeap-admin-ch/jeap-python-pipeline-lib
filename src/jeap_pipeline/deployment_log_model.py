from enum import Enum

class DeploymentTarget:
    """
    Represents a deployment target with a type, URL, and additional details.

    Attributes:
        target_type (str): The type of the deployment target.
        url (str): The URL of the deployment target.
        details (str): Additional details about the deployment target.
    """
    def __init__(self,
                 target_type: str,
                 url: str,
                 details: str):
        self.target_type: str = target_type
        self.url: str = url
        self.details: str = details

    def to_dict(self):
        return to_json({
            "type": self.target_type,
            "url": self.url,
            "details": self.details
        })

class ComponentVersion:
    """
    Represents a version of a component with various attributes.

    Attributes:
        version_name (str): The name of the version.
        tagged_at (str): The timestamp when the version was tagged.
        version_control_url (str): The URL of the version control system.
        commit_ref (str): The commit reference.
        commited_at (str): The timestamp when the commit was made.
        published_version (str): The published version.
        component_name (str): The name of the component.
        system_name (str): The name of the system.
    """
    def __init__(self,
                 version_name: str,
                 tagged_at: str,
                 version_control_url: str,
                 commit_ref: str,
                 commited_at: str,
                 published_version: str,
                 component_name: str,
                 system_name: str):
        self.version_name: str = version_name
        self.tagged_at: str = tagged_at
        self.version_control_url: str = version_control_url
        self.commit_ref: str = commit_ref
        self.commited_at: str = commited_at
        self.published_version: str = published_version
        self.component_name: str = component_name
        self.system_name: str = system_name

    def to_dict(self):
        return to_json({
            "versionName": self.version_name,
            "taggedAt": self.tagged_at,
            "versionControlUrl": self.version_control_url,
            "commitRef": self.commit_ref,
            "commitedAt": self.commited_at,
            "publishedVersion": self.published_version,
            "componentName": self.component_name,
            "systemName": self.system_name
        })

class DeploymentUnitType(Enum):
    """
    Enum representing the types of deployment units.
    """
    DOCKER_IMAGE = "DOCKER_IMAGE"
    MAVEN_JAR = "MAVEN_JAR"
    NPM_PACKAGE = "NPM_PACKAGE"
    SOURCE_BUILD = "SOURCE_BUILD"
    GIT_OPS_COMMIT = "GIT_OPS_COMMIT"

class DeploymentUnit:
    """
    Represents a deployment unit with a type, coordinates, and artifact repository URL.

    Attributes:
        type (DeploymentUnitType): The type of the deployment unit.
        coordinates (str): The coordinates of the deployment unit.
        artifact_repo_url (str): The URL of the artifact repository.
    """
    def __init__(self,
                 deployment_unit_type: DeploymentUnitType,
                 deployment_unit_coordinates: str,
                 artifact_repo_url: str):
        self.type: DeploymentUnitType = deployment_unit_type
        self.coordinates: str = deployment_unit_coordinates
        self.artifact_repo_url: str = artifact_repo_url

    @staticmethod
    def docker_image(artifact_repo_url: str):
        """
        Creates a DeploymentUnit instance for a Docker image.

        Args:
            artifact_repo_url (str): The URL of the artifact repository.

        Returns:
            DeploymentUnit: A DeploymentUnit instance for a Docker image.
        """
        url_without_prefix: str = artifact_repo_url.replace("https://", "")
        return DeploymentUnit(DeploymentUnitType.DOCKER_IMAGE, url_without_prefix, artifact_repo_url)

    @staticmethod
    def maven_jar(coordinates: str, artifact_repo_url: str):
        """
        Creates a DeploymentUnit instance for a Maven JAR.

        Args:
            coordinates (str): The coordinates of the Maven JAR.
            artifact_repo_url (str): The URL of the artifact repository.

        Returns:
            DeploymentUnit: A DeploymentUnit instance for a Maven JAR.
        """
        return DeploymentUnit(DeploymentUnitType.MAVEN_JAR, coordinates, artifact_repo_url)

    def to_dict(self):
        return to_json({
            "type": self.type.value,
            "coordinates": self.coordinates,
            "artifactRepositoryUrl": self.artifact_repo_url
        })



class Link:
    """
    Represents a link with a label and URL.

    Attributes:
        label (str): The label of the link.
        url (str): The URL of the link.
    """
    def __init__(self,
                 label: str,
                 url: str):
        self.label: str = label
        self.url: str = url

    def to_dict(self):
        return to_json({
            "label": self.label,
            "url": self.url,
        })

class ChangeLog:
    """
    Represents a changelog with version information and JIRA issue keys.

    Attributes:
        version_name (str): The name of the version.
        current_version_on_environment (str): The current version on the environment.
        changelog_jira_issue_keys (list of str): A list of JIRA issue keys related to the changelog.
    """
    def __init__(self,
                 version_name: str,
                 current_version_on_environment: str,
                 changelog_jira_issue_keys: list[str]):
        self.version_name: str = version_name
        self.current_version_on_environment: str = current_version_on_environment
        self.changelog_jira_issue_keys: list[str] = changelog_jira_issue_keys

    def to_dict(self):
        """
        Converts the ChangeLog instance to a dictionary.

        Returns:
            dict: A dictionary representation of the ChangeLog instance, or None if the current version on the environment is None.
        """
        if self.current_version_on_environment is None:
            return None

        comment = self.get_comment()
        changelog_jira_issue_keys = self.get_changelog_jira_issue_keys()

        return to_json({
            "comparedToVersion": self.current_version_on_environment,
            "comment": comment,
            "jiraIssueKeys": changelog_jira_issue_keys
        })

    def get_comment(self):
        """
        Generates a comment based on the changelog JIRA issue keys.

        Returns:
            str: A comment if no JIRA issue keys are found, otherwise None.
        """
        if self.get_changelog_jira_issue_keys() is None :
            return f"Unable to determine changelog between {self.version_name} and {self.current_version_on_environment}"
        else:
            return None

    def get_changelog_jira_issue_keys(self):
        """
        Retrieves the changelog JIRA issue keys.

        Returns:
            list of str: The changelog JIRA issue keys, or None if no keys are found.
        """
        if self.changelog_jira_issue_keys is None or len(self.changelog_jira_issue_keys) == 0 :
            return None
        else:
            return self.changelog_jira_issue_keys

class Deployment:
    """
    Represents a deployment with various attributes.

    Attributes:
        started_at (str): The timestamp when the deployment started.
        started_by (str): The user who started the deployment.
        environment_name (str): The name of the environment.
        target (DeploymentTarget): The deployment target.
        links (list of Link): A list of links related to the deployment.
        component_version (ComponentVersion): The version of the component being deployed.
        deployment_unit (DeploymentUnit): The deployment unit.
        changelog (ChangeLog): The changelog for the deployment.
        remedy_change_id (str): The remedy change ID.
        properties (dict): Additional properties of the deployment.
    """
    def __init__(self,
                 started_at: str,
                 started_by: str,
                 environment_name: str,
                 target: DeploymentTarget,
                 links: list[Link],
                 component_version: ComponentVersion,
                 deployment_unit: DeploymentUnit,
                 changelog: ChangeLog,
                 remedy_change_id: str,
                 properties: dict):
        self.started_at: str = started_at
        self.started_by: str = started_by
        self.environment_name: str = environment_name
        self.target: DeploymentTarget = target
        self.links: list[Link] = links
        self.component_version: ComponentVersion = component_version
        self.deployment_unit: DeploymentUnit = deployment_unit
        self.changelog: ChangeLog = changelog
        self.remedy_change_id: str = remedy_change_id
        self.properties: dict = properties

    def to_dict(self):
        deployment_dict = to_json({
            "startedAt": self.started_at,
            "startedBy": self.started_by,
            "environmentName": self.environment_name,
            "target": self.target,
            "links":  [link.to_dict() for link in self.links] if self.links else None,
            "componentVersion": self.component_version,
            "deploymentUnit": self.deployment_unit,
            "changelog": self.changelog,
            "properties" : self.properties
        })
        if self.remedy_change_id:
            deployment_dict["remedyChangeId"] = self.remedy_change_id
        return deployment_dict



def to_json(dictionary):
    """
    Converts a dictionary to a JSON-serializable dictionary.

    Args:
        dictionary (dict): The dictionary to convert.

    Returns:
        dict: A JSON-serializable dictionary.
    """
    def serialize_value(value):
        if isinstance(value, set):
            return list(value)  # Convert set to list
        elif hasattr(value, 'to_dict'):
            return value.to_dict()  # Serialize if it's an object with a to_dict method
        elif isinstance(value, dict):
            return to_json(value)  # Recursively serialize nested dictionaries
        else:
            return value  # Return value as is if it's serializable

    return {
        key: serialize_value(value)
        for key, value in dictionary.items() if value is not None
    }