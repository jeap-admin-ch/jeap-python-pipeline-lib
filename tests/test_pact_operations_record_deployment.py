import unittest
from unittest.mock import patch, MagicMock
from src.jeap_pipeline import pact_operations


class TestRecordDeployment(unittest.TestCase):

    @patch('src.jeap_pipeline.pact_operations.subprocess.run')
    def test_record_deployment_success(self, mock_subprocess_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_subprocess_run.return_value = mock_result

        pact_operations.record_deployment(
            pact_pacticipant_name="test_pacticipant",
            pacticipant_version="1.0.0",
            current_stage="test_env"
        )

        mock_subprocess_run.assert_called_once_with(
            [
                "pact-broker",
                "record-deployment",
                "--pacticipant", "test_pacticipant",
                "--version", "1.0.0",
                "--environment", "test_env"
            ],
            capture_output=True,
            text=True
        )

    @patch('src.jeap_pipeline.pact_operations.subprocess.run')
    def test_record_deployment_failure(self, mock_subprocess_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error"
        mock_subprocess_run.return_value = mock_result

        with self.assertRaises(RuntimeError):
            pact_operations.record_deployment(
                pact_pacticipant_name="test_pacticipant",
                pacticipant_version="1.0.0",
                current_stage="test_env"
            )

        mock_subprocess_run.assert_called_once_with(
            [
                "pact-broker",
                "record-deployment",
                "--pacticipant", "test_pacticipant",
                "--version", "1.0.0",
                "--environment", "test_env"
            ],
            capture_output=True,
            text=True
        )


if __name__ == '__main__':
    unittest.main()
