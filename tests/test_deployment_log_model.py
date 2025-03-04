import unittest

from src.jeap_pipeline import DeploymentTarget, ComponentVersion, DeploymentUnit, Deployment, ChangeLog, Link


class TestDeploymentLogOperations(unittest.TestCase):

    def test_deployment_target_to_dict(self):
        target = DeploymentTarget("type1", "http://example.com", "details")
        expected_dict = {
            "type": "type1",
            "url": "http://example.com",
            "details": "details"
        }
        self.assertEqual(target.to_dict(), expected_dict)

    def test_component_version_to_dict(self):
        version = ComponentVersion("v1.0", "2023-01-01T00:00:00Z", "http://vcs.com", "abc123", "2023-01-01T00:00:00Z", "1.0.0", "component1", "system1")
        expected_dict = {
            "versionName": "v1.0",
            "taggedAt": "2023-01-01T00:00:00Z",
            "versionControlUrl": "http://vcs.com",
            "commitRef": "abc123",
            "commitedAt": "2023-01-01T00:00:00Z",
            "publishedVersion": "1.0.0",
            "componentName": "component1",
            "systemName": "system1"
        }
        self.assertEqual(version.to_dict(), expected_dict)

    def test_deployment_unit_docker_image(self):
        unit = DeploymentUnit.docker_image("https://repo.com/image")
        expected_dict = {
            "type": "DOCKER_IMAGE",
            "coordinates": "repo.com/image",
            "artifactRepositoryUrl": "https://repo.com/image"
        }
        self.assertEqual(unit.to_dict(), expected_dict)

    def test_deployment_unit_maven_jar(self):
        unit = DeploymentUnit.maven_jar("com.example:artifact:1.0.0", "https://repo.com")
        expected_dict = {
            "type": "MAVEN_JAR",
            "coordinates": "com.example:artifact:1.0.0",
            "artifactRepositoryUrl": "https://repo.com"
        }
        self.assertEqual(unit.to_dict(), expected_dict)

    def test_link_to_dict(self):
        link = Link("example", "http://example.com")
        expected_dict = {
            "label": "example",
            "url": "http://example.com"
        }
        self.assertEqual(link.to_dict(), expected_dict)

    def test_deployment_to_dict(self):
        target = DeploymentTarget("type1", "http://example.com", {"key": "value"})
        version = ComponentVersion("v1.0", "2023-01-01T00:00:00Z", "http://vcs.com", "abc123", "2023-01-01T00:00:00Z", "1.0.0", "component1", "system1")
        unit = DeploymentUnit.docker_image("https://repo.com/image")
        changelog = ChangeLog("v1.0", "v0.9", ["JIRA-123"])
        link = Link("example", "http://example.com")
        deployment = Deployment("2023-01-01T00:00:00Z", "user1", "env1", target, [link], version, unit, changelog, "RC-123", {"key": "value"})
        expected_dict = {
            "startedAt": "2023-01-01T00:00:00Z",
            "startedBy": "user1",
            "environmentName": "env1",
            "target": target.to_dict(),
            "links": [link.to_dict()],
            "componentVersion": version.to_dict(),
            "deploymentUnit": unit.to_dict(),
            "changelog": changelog.to_dict(),
            "remedyChangeId": "RC-123",
            "properties": {"key": "value"}
        }
        self.assertEqual(deployment.to_dict(), expected_dict)

    def test_changelog_to_dict_no_keys(self):
        changelog = ChangeLog("v1.0", "v0.9", [])
        expected_dict = {
            "comparedToVersion": "v0.9",
            "comment": "Unable to determine changelog between v1.0 and v0.9",
        }
        self.assertEqual(changelog.to_dict(), expected_dict)

    def test_changelog_to_dict_no_current_version(self):
        changelog = ChangeLog("v1.0", None, ["JIRA-123"])
        self.assertIsNone(changelog.to_dict())

    def test_changelog_to_dict(self ):
        changelog = ChangeLog("v1.0", "v0.9", ["JIRA-123"])
        expected_dict = {
            "comparedToVersion": "v0.9",
            "jiraIssueKeys": ["JIRA-123"]
        }
        self.assertEqual(changelog.to_dict(), expected_dict)
