import unittest
from src.jeap_pipeline.message_contract_service_configuration import get_app_name_for_message_contract


class TestGetAppNameForMessageContract(unittest.TestCase):      

    def test_get_app_name_for_message_contract_uses_message_contract_app_name(self):
        result = get_app_name_for_message_contract(
            message_contract_app_name="test_app_name",
            message_contract_app_names={"test_env": "mapped_test_app_name"},
            app_name="test_env"
        )
        self.assertEqual(result, "test_app_name")

    def test_get_app_name_for_message_contract_is_mapped(self):
        result = get_app_name_for_message_contract(
            message_contract_app_name=None,
            message_contract_app_names={"test_env": "mapped_test_app_name"},
            app_name="test_env"
        )
        self.assertEqual(result, "mapped_test_app_name")

    def test_get_app_name_for_message_contract_is_not_mapped(self):
        result = get_app_name_for_message_contract(
            message_contract_app_name=None,
            message_contract_app_names={"test_env": "mapped_test_app_name"},
            app_name="dev_env"
        )
        self.assertEqual(result, "dev_env")

if __name__ == '__main__':
    unittest.main()
