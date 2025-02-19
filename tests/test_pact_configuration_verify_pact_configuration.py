import unittest
from src.jeap_pipeline.pact_configuration import verify_pact_configuration


class TestVerifyPactConfiguration(unittest.TestCase):

    def test_verify_valid_configuration(self):
        try:
            verify_pact_configuration(
                pact_pacticipants=["service1", "service2"],
                is_pact_pacticipant=False,
                services=["service1", "service2", "service3"]
            )
        except ValueError:
            self.fail("verify_pact_configuration raised ValueError unexpectedly!")

    def test_verify_invalid_configuration(self):
        with self.assertRaises(ValueError):
            verify_pact_configuration(
                pact_pacticipants=["service1", "invalid_service"],
                is_pact_pacticipant=False,
                services=["service1", "service2", "service3"]
            )

    def test_verify_no_pact_pacticipants(self):
        try:
            verify_pact_configuration(
                pact_pacticipants=[],
                is_pact_pacticipant=False,
                services=["service1", "service2", "service3"]
            )
        except ValueError:
            self.fail("verify_pact_configuration raised ValueError unexpectedly!")

    def test_verify_is_pact_pacticipant(self):
        try:
            verify_pact_configuration(
                pact_pacticipants=["service1", "service2"],
                is_pact_pacticipant=True,
                services=["service1", "service2", "service3"]
            )
        except ValueError:
            self.fail("verify_pact_configuration raised ValueError unexpectedly!")


if __name__ == '__main__':
    unittest.main()
