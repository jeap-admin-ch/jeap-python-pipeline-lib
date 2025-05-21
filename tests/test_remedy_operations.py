import unittest
from unittest.mock import patch, Mock

from src.jeap_pipeline import (create_change_request_in_remedy, get_change_request_id_from_response)


class TestRemedyOperations(unittest.TestCase):


    @patch('src.jeap_pipeline.remedy_operations.request')
    def test_create_change_request_in_remedy_success(self, mock_request):

        # Create a mock response object
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<Infrastructure_Change_ID>UNIT_TEST_01</Infrastructure_Change_ID>"

        mock_request.return_value = mock_response

        cr_id = create_change_request_in_remedy("https://example.com", "<test>test</test>")
        mock_request.assert_called_with(
            method='POST',
            url='https://example.com',
            data='<test>test</test>',
            headers={'Content-Type': 'text/xml; charset=UTF-8', 'SOAPAction': 'urn:CHG_ChangeInterface_Create_WS/Change_Submit_Service'}
        )
        self.assertEqual(cr_id, "UNIT_TEST_01")


    @patch('src.jeap_pipeline.remedy_operations.request')
    def test_create_change_request_in_remedy_none(self, mock_request):

        # Create a mock response object
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "foo"

        mock_request.return_value = mock_response

        cr_id = create_change_request_in_remedy("https://example.com", "<test>test</test>")
        mock_request.assert_called_with(
            method='POST',
            url='https://example.com',
            data='<test>test</test>',
            headers={'Content-Type': 'text/xml; charset=UTF-8', 'SOAPAction': 'urn:CHG_ChangeInterface_Create_WS/Change_Submit_Service'}
        )
        self.assertIsNone(cr_id)


    def test_get_change_request_id_from_response(self):
        self.assertIsNone(get_change_request_id_from_response("foobar"))
        self.assertEqual(get_change_request_id_from_response("<Infrastructure_Change_ID>UNIT_TEST_01</Infrastructure_Change_ID>"), "UNIT_TEST_01")