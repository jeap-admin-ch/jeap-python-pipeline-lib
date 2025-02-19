import unittest
from unittest.mock import patch, MagicMock
from src.jeap_pipeline import pact_operations


class TestDoCanIDeployCheck(unittest.TestCase):

    @patch('src.jeap_pipeline.pact_operations.subprocess.run')
    def test_do_can_i_deploy_check_success(self, mock_subprocess_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Success"
        mock_subprocess_run.return_value = mock_result

        pact_operations.do_can_i_deploy_check(
            pact_pacticipant_name="test_pacticipant",
            pacticipant_version="1.0.0",
            current_stage="test_env"
        )

        mock_subprocess_run.assert_called_once_with(
            [
                "pact-broker",
                "can-i-deploy",
                "--pacticipant", "test_pacticipant",
                "--version", "1.0.0",
                "--to-environment", "test_env",
                "--retry-while-unknown", "6",
                "--retry-interval", "5"
            ],
            capture_output=True,
            text=True
        )

    @patch('src.jeap_pipeline.pact_operations.subprocess.run')
    def test_do_can_i_deploy_check_failure(self, mock_subprocess_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error"
        mock_subprocess_run.return_value = mock_result

        with self.assertRaises(ValueError):
            pact_operations.do_can_i_deploy_check(
                pact_pacticipant_name="test_pacticipant",
                pacticipant_version="1.0.0",
                current_stage="test_env"
            )

        mock_subprocess_run.assert_called_once_with(
            [
                "pact-broker",
                "can-i-deploy",
                "--pacticipant", "test_pacticipant",
                "--version", "1.0.0",
                "--to-environment", "test_env",
                "--retry-while-unknown", "6",
                "--retry-interval", "5"
            ],
            capture_output=True,
            text=True
        )


if __name__ == '__main__':
    unittest.main()
