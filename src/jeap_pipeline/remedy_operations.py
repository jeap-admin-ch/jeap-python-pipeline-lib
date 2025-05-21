import re
from typing import Optional

from requests import request, Response


def create_change_request_in_remedy(url: str, request_xml: str) -> Optional[str]:
    """
    Post a new web service request to remedy.

    Args:
        url (str): The URL of the Remedy web service.
        request_xml (str): xml content with the request.

    Returns:
        Change request ID from Remedy.
    """

    headers = {"Content-Type": "text/xml; charset=UTF-8",
               "SOAPAction": "urn:CHG_ChangeInterface_Create_WS/Change_Submit_Service"}
    response : Response = request(method='POST', url=url, data=request_xml, headers=headers)

    if response.status_code >= 400:
        print(f"Request failed with status code {response.status_code}: {response.text}")
        response.raise_for_status()

    print("Change request successfully published in Remedy")
    print(f"Received response from remedy: {response.text}")
    return get_change_request_id_from_response(response.text)


def get_change_request_id_from_response(remedy_xml_response: str) -> Optional[str]:
    match = re.compile(r"Infrastructure_Change_ID>(.*?)</", re.DOTALL).search(remedy_xml_response)
    return match.group(1).strip() if match else None