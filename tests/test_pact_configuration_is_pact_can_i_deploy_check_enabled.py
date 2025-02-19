import unittest
from src.jeap_pipeline.pact_configuration import is_pact_can_i_deploy_check_enabled


class TestIsPactCanIDeployCheckEnabled(unittest.TestCase):

    def test_check_enabled(self):
        result = is_pact_can_i_deploy_check_enabled(
            environment="test_env",
            pact_can_i_deploy_check_environments=["test_env", "prod_env"]
        )
        self.assertTrue(result)

    def test_check_disabled(self):
        result = is_pact_can_i_deploy_check_enabled(
            environment="dev_env",
            pact_can_i_deploy_check_environments=["test_env", "prod_env"]
        )
        self.assertFalse(result)

    def test_check_no_environments(self):
        result = is_pact_can_i_deploy_check_enabled(
            environment="test_env",
            pact_can_i_deploy_check_environments=[]
        )
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
