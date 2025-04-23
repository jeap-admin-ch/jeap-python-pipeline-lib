import unittest
from src.jeap_pipeline.message_contract_service_configuration import is_message_contract_compatibility_check_enabled


class TestIsMessageContractCompatibilityCheckEnabled(unittest.TestCase):

    def test_check_enabled(self):
        result = is_message_contract_compatibility_check_enabled(
            environment="test_env",
            message_contract_compatibility_check_environments=["test_env", "prod_env"]
        )
        self.assertTrue(result)

    def test_check_disabled(self):
        result = is_message_contract_compatibility_check_enabled(
            environment="dev_env",
            message_contract_compatibility_check_environments=["test_env", "prod_env"]
        )
        self.assertFalse(result)

    def test_check_no_environments(self):
        result = is_message_contract_compatibility_check_enabled(
            environment="test_env",
            message_contract_compatibility_check_environments=[]
        )
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
