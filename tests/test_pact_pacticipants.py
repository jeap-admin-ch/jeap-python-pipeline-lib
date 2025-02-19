import unittest

from src.jeap_pipeline import pact_pacticipants


class TestGetPacticipantNames(unittest.TestCase):

    def test_single_pacticipant_name(self):
        result = pact_pacticipants.get_pacticipant_names(
            app_name="app1",
            department="dept1",
            pact_pacticipant_name=None,
            pact_pacticipant_names=[],
            pact_provider_api_names=[]
        )
        self.assertEqual(result, ["dept1-app1"])

    def test_single_pacticipant_name_with_specific_name(self):
        result = pact_pacticipants.get_pacticipant_names(
            app_name="app1",
            department="dept1",
            pact_pacticipant_name="specific_name",
            pact_pacticipant_names=[],
            pact_provider_api_names=[]
        )
        self.assertEqual(result, ["specific_name"])

    def test_multiple_pacticipant_names(self):
        result = pact_pacticipants.get_pacticipant_names(
            app_name="app1",
            department="dept1",
            pact_pacticipant_name=None,
            pact_pacticipant_names=[],
            pact_provider_api_names=["api1", "api2"]
        )
        self.assertEqual(result, ["dept1-app1_api1", "dept1-app1_api2"])

    def test_pacticipant_names_from_dict(self):
        result = pact_pacticipants.get_pacticipant_names(
            app_name="app1",
            department="dept1",
            pact_pacticipant_name=None,
            pact_pacticipant_names={"app1": "custom_name"},
            pact_provider_api_names=[]
        )
        self.assertEqual(result, ["custom_name"])

    def test_pacticipant_names_from_dict_with_apis(self):
        result = pact_pacticipants.get_pacticipant_names(
            app_name="app1",
            department="dept1",
            pact_pacticipant_name=None,
            pact_pacticipant_names={"app1": "custom_name"},
            pact_provider_api_names=["api1", "api2"]
        )
        self.assertEqual(result, ["custom_name_api1", "custom_name_api2"])

    def test_pacticipant_names_with_multiple_entries_and_apis(self):
        result = pact_pacticipants.get_pacticipant_names(
            app_name="app2",
            department="dept2",
            pact_pacticipant_name=None,
            pact_pacticipant_names={"app1": "custom_name1", "app2": "custom_name2"},
            pact_provider_api_names=["api1", "api2"]
        )
        self.assertEqual(result, ["custom_name2_api1", "custom_name2_api2"])


if __name__ == '__main__':
    unittest.main()
