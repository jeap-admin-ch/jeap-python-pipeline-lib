import json
import unittest
from unittest.mock import MagicMock, patch

import requests

from jeap_pipeline.oauth_token import OAuthTokenError, fetch_client_credentials_token

TOKEN_URI = "https://internal-csp.jme-dev.nivel.bazg.admin.ch/jme-nivel-doc-auth-scs/oauth2/token"
SECRET = "the-very-secret-value"


def _response(status_code, body=None, text=None):
    response = MagicMock()
    response.status_code = status_code
    response.text = text if text is not None else json.dumps(body or {})
    if body is None and text is not None:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = body or {}
    return response


class FetchClientCredentialsTokenTest(unittest.TestCase):

    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_posts_the_client_credentials_grant_as_form_parameters(self, post):
        post.return_value = _response(200, {"access_token": "a-token"})

        token = fetch_client_credentials_token(TOKEN_URI, "jme-doc-pipeline", SECRET)

        self.assertEqual("a-token", token)
        self.assertEqual(TOKEN_URI, post.call_args[0][0])
        self.assertEqual({"grant_type": "client_credentials", "client_id": "jme-doc-pipeline",
                          "client_secret": SECRET}, post.call_args[1]["data"])
        self.assertEqual((5, 30), post.call_args[1]["timeout"])

    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_a_scope_is_sent_only_when_it_is_given(self, post):
        post.return_value = _response(200, {"access_token": "a-token"})

        fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET, scope="openid")
        self.assertEqual("openid", post.call_args[1]["data"]["scope"])

        fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET)
        self.assertNotIn("scope", post.call_args[1]["data"])

    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_a_401_says_that_the_client_pair_is_wrong_without_naming_the_secret(self, post):
        post.return_value = _response(401, text="unauthorized_client")

        with self.assertRaises(OAuthTokenError) as raised:
            fetch_client_credentials_token(TOKEN_URI, "jme-doc-pipeline", SECRET)

        message = str(raised.exception)
        self.assertIn("jme-doc-pipeline", message)
        self.assertIn("client id and secret pair", message)
        self.assertNotIn(SECRET, message)

    @patch("jeap_pipeline.oauth_token.time.sleep")
    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_a_500_is_reported_with_the_status(self, post, sleep):
        post.return_value = _response(500, text="boom")

        with self.assertRaises(OAuthTokenError) as raised:
            fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET, attempts=1)

        self.assertIn("status 500", str(raised.exception))
        self.assertNotIn(SECRET, str(raised.exception))

    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_redirects_are_not_followed_so_the_body_is_never_re_sent(self, post):
        post.return_value = _response(200, {"access_token": "a-token"})

        fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET)

        self.assertFalse(post.call_args[1]["allow_redirects"],
                         "a 307 would re-send the body, and the body holds the client secret")

    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_an_answer_without_a_token_is_reported(self, post):
        post.return_value = _response(200, {"token_type": "Bearer"})

        with self.assertRaises(OAuthTokenError) as raised:
            fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET)

        self.assertIn("without an access token", str(raised.exception))

    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_an_answer_that_is_not_json_is_reported(self, post):
        post.return_value = _response(200, text="<html>login page</html>")

        with self.assertRaises(OAuthTokenError) as raised:
            fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET)

        self.assertIn("not JSON", str(raised.exception))

    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_json_that_is_not_an_object_is_reported(self, post):
        post.return_value = _response(200, ["not", "an", "object"])

        with self.assertRaises(OAuthTokenError) as raised:
            fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET)

        self.assertIn("not an object", str(raised.exception))

    @patch("jeap_pipeline.oauth_token.time.sleep")
    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_an_unreachable_authorization_server_does_not_chain_the_request(self, post, sleep):
        # The requests exception carries the prepared request, whose body holds the secret.
        exception = requests.exceptions.ConnectionError("no route to host")
        exception.request = MagicMock(body=f"client_secret={SECRET}")
        post.side_effect = exception

        with self.assertRaises(OAuthTokenError) as raised:
            fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET, attempts=2)

        self.assertIsNone(raised.exception.__cause__)
        self.assertIsNone(raised.exception.__context__,
                          "the chained request, whose body holds the secret, is not printed")
        self.assertIn("ConnectionError", str(raised.exception))
        self.assertNotIn(SECRET, str(raised.exception))


class RetryTest(unittest.TestCase):
    """An authorization server is deployed like any other service, and a restart is not a failure."""

    @patch("jeap_pipeline.oauth_token.time.sleep")
    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_a_server_error_that_recovers_is_a_token(self, post, sleep):
        post.side_effect = [_response(503, text="restarting"),
                            _response(200, {"access_token": "a-token"})]

        self.assertEqual("a-token", fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET))
        self.assertEqual(2, post.call_count)

    @patch("jeap_pipeline.oauth_token.time.sleep")
    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_a_connection_error_that_recovers_is_a_token(self, post, sleep):
        post.side_effect = [requests.exceptions.ConnectionError("no route to host"),
                            _response(200, {"access_token": "a-token"})]

        self.assertEqual("a-token", fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET))
        self.assertEqual(2, post.call_count)

    @patch("jeap_pipeline.oauth_token.time.sleep")
    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_a_server_error_is_tried_three_times_and_then_raises(self, post, sleep):
        post.return_value = _response(503, text="Service Unavailable")

        with self.assertRaises(OAuthTokenError) as raised:
            fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET)

        self.assertEqual(3, post.call_count)
        self.assertEqual(2, sleep.call_count)
        self.assertIn("in 3 attempt(s)", str(raised.exception))

    @patch("jeap_pipeline.oauth_token.time.sleep")
    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_a_refusal_is_not_retried(self, post, sleep):
        post.return_value = _response(401, text="unauthorized_client")

        with self.assertRaises(OAuthTokenError):
            fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET)

        self.assertEqual(1, post.call_count, "a wrong client pair does not become right by asking again")
        sleep.assert_not_called()

    @patch("jeap_pipeline.oauth_token.time.sleep")
    @patch("builtins.print")
    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_nothing_logged_while_retrying_carries_the_secret(self, post, printed, sleep):
        exception = requests.exceptions.ConnectionError("no route to host")
        exception.request = MagicMock(body=f"client_secret={SECRET}")
        post.side_effect = exception

        with self.assertRaises(OAuthTokenError):
            fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET, attempts=2)

        for call in printed.call_args_list:
            self.assertNotIn(SECRET, " ".join(str(argument) for argument in call[0]))

    def test_a_missing_input_is_reported_before_anything_is_called(self):
        with self.assertRaises(OAuthTokenError):
            fetch_client_credentials_token("", "a-client", SECRET)
        with self.assertRaises(OAuthTokenError):
            fetch_client_credentials_token(TOKEN_URI, "", SECRET)
        with self.assertRaises(OAuthTokenError) as raised:
            fetch_client_credentials_token(TOKEN_URI, "a-client", "")
        self.assertIn("No client secret", str(raised.exception))

    @patch("builtins.print")
    @patch("jeap_pipeline.oauth_token.requests.post")
    def test_nothing_logged_carries_the_secret(self, post, printed):
        post.return_value = _response(200, {"access_token": "a-token"})

        fetch_client_credentials_token(TOKEN_URI, "a-client", SECRET)

        for call in printed.call_args_list:
            self.assertNotIn(SECRET, " ".join(str(argument) for argument in call[0]))


if __name__ == "__main__":
    unittest.main()
