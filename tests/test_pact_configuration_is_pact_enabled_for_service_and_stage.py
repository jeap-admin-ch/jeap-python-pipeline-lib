import unittest
from src.jeap_pipeline.pact_configuration import is_pact_enabled_for_service_and_stage


class TestIsPactEnabledForServiceAndStage(unittest.TestCase):

    def test_pact_enabled(self):
        result = is_pact_enabled_for_service_and_stage(
            current_stage="test_env",
            service_name="test_service",
            pact_environments=["test_env", "prod_env"],
            is_pact_pacticipant=True,
            pact_pacticipants=[]
        )
        self.assertTrue(result)

    def test_pact_disabled(self):
        result = is_pact_enabled_for_service_and_stage(
            current_stage="dev_env",
            service_name="test_service",
            pact_environments=["test_env", "prod_env"],
            is_pact_pacticipant=False,
            pact_pacticipants=[]
        )
        self.assertFalse(result)

    def test_pact_enabled_for_service(self):
        result = is_pact_enabled_for_service_and_stage(
            current_stage="test_env",
            service_name="test_service",
            pact_environments=["test_env", "prod_env"],
            is_pact_pacticipant=False,
            pact_pacticipants=["test_service"]
        )
        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
