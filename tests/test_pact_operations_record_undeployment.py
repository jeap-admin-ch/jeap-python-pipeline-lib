import unittest
from unittest.mock import patch, MagicMock
from src.jeap_pipeline import pact_operations


class TestRecordUndeployment(unittest.TestCase):

    @patch('src.jeap_pipeline.pact_operations.subprocess.run')
    def test_record_undeployment_success(self, mock_subprocess_run):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Undeployment recorded successfully"
        mock_subprocess_run.return_value = mock_result

        pact_operations.record_undeployment(
            pact_pacticipant_name="test_pacticipant",
            current_stage="test_env"
        )

        mock_subprocess_run.assert_called_once_with(
            [
                "pact-broker",
                "record-undeployment",
                "--pacticipant", "test_pacticipant",
                "--environment", "test_env"
            ],
            capture_output=True,
            text=True
        )

    @patch('src.jeap_pipeline.pact_operations.subprocess.run')
    def test_record_undeployment_failure(self, mock_subprocess_run):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Undeployment failed"
        mock_subprocess_run.return_value = mock_result

        with self.assertRaises(RuntimeError):
            pact_operations.record_undeployment(
                pact_pacticipant_name="test_pacticipant",
                current_stage="test_env"
            )

        mock_subprocess_run.assert_called_once_with(
            [
                "pact-broker",
                "record-undeployment",
                "--pacticipant", "test_pacticipant",
                "--environment", "test_env"
            ],
            capture_output=True,
            text=True
        )


if __name__ == '__main__':
    unittest.main()
