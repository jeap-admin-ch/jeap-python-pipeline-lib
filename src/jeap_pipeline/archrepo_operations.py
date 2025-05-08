from requests import request, Response
from requests.auth import HTTPBasicAuth
import json

def post_openapi_spec_to_archrepo_service(url: str,
                                          system_name: str,
                                          component_name: str,
                                          version: str,
                                          open_api_spec_json: dict,
                                          username: str,
                                          password: str) -> Response:
    """
    Upload a new OpenAPI spec for a system component in the ArchRepo service.

    Args:
        url (str): The base URL of the ArchRepo service.
        system_name (str): The system name of the component.
        component_name (str): The component name of the component.
        version (str): The version of the OpenAPI spec.
        open_api_spec_json (dict): The JSON data containing the OpenAPI spec.
        username (str): The username for authentication on the ArchRepo service.
        password (str): The password for authentication on the ArchRepo service.

    Returns:
        Response: The response from the ArchRepo service.
    """
    api_url = f"{url}/api/openapi/{system_name}/{component_name}?version={version}"
    print(f"Upload OpenAPI Spec with url: {api_url}")

    # Pack the json data in multipart files
    request_body_multipart_files: dict = {
        "file": ("openapi.json", json.dumps(open_api_spec_json), "application/json"),
    }

    auth = HTTPBasicAuth(username, password)
    response = request("POST", api_url, files=request_body_multipart_files, auth=auth)
    if response.status_code >= 400:
        print(f"Request failed with status code {response.status_code}: {response.text}")
        response.raise_for_status()
    print("OpenAPI Spec successfully uploaded")
    return response