from datetime import datetime
import json
import unittest
from unittest.mock import patch, Mock

from src.jeap_pipeline import (put_deployment_state,
                               put_to_deployment_log_service,
                               get_previous_deployment_on_environment,
                               put_artifacts_version,
                               get_actual_timestamp,
                               generate_deployment_id,
                               create_deployment_json,
                               create_change_log,
                               get_commit_details,
                               get_tagged_at)



class TestDeploymentLogOperations(unittest.TestCase):
    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def test_put_deployment_state_success(self, mock_request):
        mock_request.return_value.status_code = 200
        response = put_deployment_state("https://example.com", "123", "DEPLOYED", "user", "pass")
        self.assertEqual(response.status_code, 200)

    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def test_put_deployment_state_with_message(self, mock_request):
        mock_request.return_value.status_code = 200
        response = put_deployment_state("https://example.com", "123", "DEPLOYED", "user", "pass", message="Deployment successful")
        self.assertEqual(response.status_code, 200)

    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def test_put_to_deployment_log_service_success(self, mock_request):
        mock_request.return_value.status_code = 200
        response = put_to_deployment_log_service("https://example.com", "123", {"key": "value"}, "user", "pass")
        mock_request.assert_called_with('https://example.com/api/deployment/123?readyForDeployCheck=false', 'PUT', {'key': 'value'}, 'user', 'pass')
        self.assertEqual(response.status_code, 200)

    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def test_put_to_deployment_log_service_ready_for_deploy(self, mock_request):
        mock_request.return_value.status_code = 200
        response = put_to_deployment_log_service("https://example.com", "123", {"key": "value"}, "user", "pass", True)
        mock_request.assert_called_with('https://example.com/api/deployment/123?readyForDeployCheck=true', 'PUT', {'key': 'value'}, 'user', 'pass')
        self.assertEqual(response.status_code, 200)

    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def test_get_previous_deployment_on_environment_found(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({"deployment": "data"})
        mock_request.return_value = mock_response
        response = get_previous_deployment_on_environment("https://example.com", "system", "component", "env", "1.0", "user", "pass")
        self.assertIsNotNone(response)
        self.assertEqual(response["deployment"], "data")

    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def test_get_previous_deployment_on_environment_not_found(self, mock_request):
        mock_response = Mock()
        mock_response.status_code = 404
        mock_request.return_value = mock_response
        response = get_previous_deployment_on_environment("https://example.com", "system", "component", "env", "1.0", "user", "pass")
        self.assertIsNone(response)

    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def put_artifacts_version_success(self, mock_request):
        mock_request.return_value.status_code = 200
        response = put_artifacts_version("https://example.com", "coordinates", "https://build.url", "user", "pass")
        self.assertEqual(response.status_code, 200)

    @patch('src.jeap_pipeline.deployment_log_operations.__request_deployment_log_service')
    def put_artifacts_version_failure(self, mock_request):
        mock_request.return_value.status_code = 500
        response = put_artifacts_version("https://example.com", "coordinates", "https://build.url", "user", "pass")
        self.assertEqual(response.status_code, 500)

    def test_actual_timestamp_format(self):
        timestamp = get_actual_timestamp()
        try:
            datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
            valid_format = True
        except ValueError:
            valid_format = False
        self.assertTrue(valid_format)

    def test_deployment_id_format(self):
        component_name = "test-component"
        env = "dev"
        deployment_id = generate_deployment_id(component_name, env)
        self.assertTrue(deployment_id.startswith("test-component-dev-"))
        self.assertEqual(len(deployment_id.split("-")), 6)

    @patch('src.jeap_pipeline.deployment_log_operations.get_previous_deployment_on_environment')
    def test_deployment_json_structure(self, mock_get_previous_deployment):
        mock_get_previous_deployment.return_value = {
            'componentVersion': {
                'commitRef': 'previous_commit_sha',
                'versionName': 'previous_version'
            }
        }

        deployment_platform = "AWS"
        actual_timestamp = "2023-10-01T12:00:00.000Z"
        system_name = "test-system"
        app_name = "test-app"
        cluster = "test-cluster"
        deploy_stage = "test-stage"
        git_commit = "test_commit_sha"
        git_commit_timestamp = "2023-10-01T11:00:00.000Z"
        version_control_url = "https://example.com/vcs"
        pipeline_run_url = "https://example.com/pipeline"
        started_by = "test-user"
        image_tag_aws = "test-image-tag"
        git_tag_timestamp = "2023-10-01T10:00:00.000Z"
        maven_published = "1.0.0"
        remedy_change_id = "test-remedy-id"
        aws_url = "https://example.com/aws"
        artifact_url = "https://example.com/artifact"
        deployment_log_url = "https://example.com/deployment-log"
        dl_username = "user"
        dl_password = "pass"

        deployment_json = create_deployment_json(deployment_platform,
            actual_timestamp, system_name, app_name, cluster, deploy_stage, git_commit, git_commit_timestamp,
            version_control_url, pipeline_run_url, started_by, image_tag_aws, git_tag_timestamp, maven_published,
            remedy_change_id, aws_url, artifact_url, deployment_log_url, dl_username, dl_password
        )

        self.assertIn("startedAt", deployment_json)
        self.assertIn("startedBy", deployment_json)
        self.assertIn("environmentName", deployment_json)
        self.assertIn("target", deployment_json)
        self.assertIn("links", deployment_json)
        self.assertIn("componentVersion", deployment_json)
        self.assertIn("deploymentUnit", deployment_json)
        self.assertIn("changelog", deployment_json)
        self.assertIn("remedyChangeId", deployment_json)

    @patch('src.jeap_pipeline.deployment_log_operations.get_previous_deployment_on_environment')
    @patch('subprocess.run')
    def test_create_change_log(self, mock_subprocess_run, mock_get_previous_deployment):
        mock_get_previous_deployment.return_value = {
            'componentVersion': {
                'commitRef': 'previous_commit_sha',
                'versionName': 'previous_version'
            }
        }
        mock_subprocess_run.return_value = Mock(stdout="JIRA-1234\nJIRA-5678\n")

        actual_version = "1.0.0"
        actual_git_commit = "current_commit_sha"
        system_name = "test-system"
        app_name = "test-app"
        deploy_stage = "test-stage"
        deployment_log_url = "https://example.com/deployment-log"
        username = "user"
        password = "pass"

        changelog = create_change_log(
            actual_version, actual_git_commit, system_name, app_name, deploy_stage, deployment_log_url, username, password
        )

        self.assertIn("comparedToVersion", changelog)
        self.assertIn("jiraIssueKeys", changelog)
        self.assertEqual(changelog["comparedToVersion"], "previous_version")
        self.assertEqual(changelog["jiraIssueKeys"], ["JIRA-1234", "JIRA-5678"])


    @patch('src.jeap_pipeline.deployment_log_operations.subprocess.run')
    def test_get_commit_details(self, mock_subprocess_run):
        # Mock the output of the subprocess.run function
        mock_subprocess_run.return_value = Mock(stdout="2023-10-01T12:00:00Z|John Doe\n")

        commit_sha = "test_commit_sha"
        commit_timestamp, committer_name = get_commit_details(commit_sha)

        self.assertEqual(commit_timestamp, "2023-10-01T12:00:00Z")
        self.assertEqual(committer_name, "John Doe")

    @patch('src.jeap_pipeline.deployment_log_operations.subprocess.run')
    def test_get_tagged_at(self, mock_subprocess_run):
        # Mock the output of the subprocess.run function
        mock_subprocess_run.return_value = Mock(stdout="2023-10-01T12:00:00Z\n")

        version_name = "1.0.0"
        tag_timestamp = get_tagged_at(version_name)

        self.assertEqual(tag_timestamp, "2023-10-01T12:00:00Z")
