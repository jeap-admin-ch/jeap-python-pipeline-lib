"""OAuth 2.0 access tokens for pipeline calls to jEAP services.

The module is deliberately free of any knowledge about the service being called: a pipeline that has
to authenticate itself against any jEAP service with a client of its own can use it, and the caller
decides which authorization server issues the token and what to do with it.
"""

import time
from typing import Optional, Tuple

import requests

#: Connect and read timeout of a token request, in seconds. A pipeline that cannot reach its
#: authorization server has to fail rather than hang until the job is killed by the runner.
DEFAULT_TIMEOUT: Tuple[int, int] = (5, 30)

#: How often a token is asked for when the authorization server cannot be reached or answers with a
#: server error. An authorization server is deployed like any other service, and a pipeline that
#: failed while one is being restarted would report a problem with the documentation that is none.
DEFAULT_ATTEMPTS = 3

_GRANT_TYPE_CLIENT_CREDENTIALS = "client_credentials"


class OAuthTokenError(RuntimeError):
    """Raised when no access token could be obtained."""


def fetch_client_credentials_token(token_uri: str,
                                   client_id: str,
                                   client_secret: str,
                                   scope: Optional[str] = None,
                                   timeout: Tuple[int, int] = DEFAULT_TIMEOUT,
                                   attempts: int = DEFAULT_ATTEMPTS,
                                   backoff_seconds: int = 2) -> str:
    """
    Obtain an access token with the OAuth 2.0 client credentials grant.

    The credentials are sent in the request body as form parameters, which is what the jEAP
    authorization servers and the jEAP OAuth mock server expect.

    Args:
        token_uri (str): The token endpoint of the authorization server, for instance
            `https://internal-csp.example.ch/auth-service/oauth2/token`.
        client_id (str): The client the pipeline authenticates as.
        client_secret (str): The secret of that client. It is never logged and never part of an
            error message.
        scope (str, optional): The scope to ask for. Some authorization servers - Keycloak among
            them - are configured to require `openid`; others need no scope at all, which is the
            default.
        timeout (tuple, optional): Connect and read timeout in seconds. Defaults to
            `DEFAULT_TIMEOUT`.
        attempts (int, optional): How often to try when the authorization server cannot be reached
            or answers with a server error. A refusal - a wrong client pair above all - is not
            retried. Defaults to `DEFAULT_ATTEMPTS`.
        backoff_seconds (int, optional): Seconds to wait between attempts.

    Raises:
        OAuthTokenError: If the request fails, if the answer is not a success, or if it carries no
            access token.

    Returns:
        str: The access token, to be sent as `Authorization: Bearer <token>`.
    """
    if not token_uri:
        raise OAuthTokenError("No token endpoint given.")
    if not client_id:
        raise OAuthTokenError("No client id given.")
    if not client_secret:
        raise OAuthTokenError(f"No client secret given for the client '{client_id}'.")

    payload = {
        "grant_type": _GRANT_TYPE_CLIENT_CREDENTIALS,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if scope:
        payload["scope"] = scope

    print(f"Requesting an access token for the client '{client_id}' from {token_uri}")

    attempts = max(1, attempts)
    response = None
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            # Redirects are not followed: a 307 or 308 would re-send the body, and the body holds
            # the client secret.
            response = requests.post(token_uri, data=payload,
                                     headers={"Accept": "application/json"},
                                     timeout=timeout, allow_redirects=False)
        except requests.exceptions.RequestException as exception:
            # The exception carries the prepared request, whose body holds the client secret, so it
            # is not chained and not printed: only its type and message are reported.
            last_error = f"{type(exception).__name__}: {exception}"
            response = None
        else:
            if response.status_code < 500:
                break
            last_error = f"status {response.status_code}: {_first_line(response.text)}"
            response = None

        print(f"Attempt {attempt} of {attempts} did not get a token: {last_error}")
        if attempt < attempts:
            time.sleep(backoff_seconds)

    if response is None:
        raise OAuthTokenError(
            f"The token endpoint {token_uri} did not issue a token for the client '{client_id}' in "
            f"{attempts} attempt(s). Last: {last_error}")

    if response.status_code != 200:
        raise OAuthTokenError(
            f"The token endpoint {token_uri} refused to issue a token for the client "
            f"'{client_id}' (status {response.status_code}): {_first_line(response.text)}"
            + (". A 401 means the client id and secret pair is not the one the authorization "
               "server knows." if response.status_code == 401 else ""))

    try:
        answer = response.json()
    except ValueError:
        raise OAuthTokenError(
            f"The token endpoint {token_uri} answered with something that is not JSON: "
            f"{_first_line(response.text)}") from None

    if not isinstance(answer, dict):
        raise OAuthTokenError(
            f"The token endpoint {token_uri} answered with JSON that is not an object: "
            f"{_first_line(response.text)}")

    access_token = answer.get("access_token")

    if not access_token:
        raise OAuthTokenError(
            f"The token endpoint {token_uri} answered without an access token: "
            f"{_first_line(response.text)}")

    return access_token


def _first_line(text: str, limit: int = 500) -> str:
    """Return the answer of a server in one line, short enough to belong in an error message."""
    if not text:
        return "<empty body>"
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit] + "…"
