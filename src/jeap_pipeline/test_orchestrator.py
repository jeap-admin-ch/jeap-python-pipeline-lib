import time
import requests
import logging
from typing import List, Dict

# ----- Default Logger Configuration -----
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ----- Constants -----
RETRY_COUNT: int = 3
SLEEP_INTERVAL: int = 5  # in seconds
NO_RESULT: str = "NO_RESULT"
PASS: str = "PASS"

def start_test_case(
        test_case: str,
        test_orchestrator_url: str,
        retry_count: int = RETRY_COUNT,
        sleep_interval: int = SLEEP_INTERVAL
) -> str:
    """
    Starts a single test case via HTTP POST request to the test orchestrator.

    Args:
        test_case (str): The name of the test case to start.
        test_orchestrator_url (str): The base URL of the test orchestrator.
        retry_count (int): Number of retry attempts on failure (default: 3).
        sleep_interval (int): Wait time between retries in seconds (default: 5).

    Returns:
        str: The test ID if successfully started.

    Raises:
        ValueError: If no test orchestrator URL is provided.
        ConnectionError: If the test case could not be started after retries.
    """
    if not test_orchestrator_url:
        raise ValueError(f"No URL provided for test case '{test_case}'.")

    for attempt in range(retry_count):
        try:
            response = requests.post(f"{test_orchestrator_url}/{test_case}", timeout=10)
            if response.status_code == 200:
                test_id = response.text.strip()
                if test_id:
                    logger.info(f"Started test case '{test_case}' with test ID '{test_id}'")
                    return test_id
        except requests.RequestException as e:
            logger.warning(f"Attempt {attempt + 1} failed for test case '{test_case}': {e}")
        time.sleep(sleep_interval)

    raise ConnectionError(f"Failed to start test case '{test_case}' after {retry_count} attempts.")

def wait_until_test_case_ends(
        test_id: str,
        test_orchestrator_url: str,
        timeout_minutes: int,
        sleep_interval: int = SLEEP_INTERVAL
) -> str:
    """
    Polls the test orchestrator until the test case result is available or timeout is reached.

    Args:
        test_id (str): The ID of the test case to monitor.
        test_orchestrator_url (str): The base URL of the test orchestrator.
        timeout_minutes (int): Maximum time to wait for the test result in minutes.
        sleep_interval (int): Time to wait between polling attempts in seconds (default: 5).

    Returns:
        str: The result of the test case (e.g., "PASS", "FAIL").
             Returns 'NO_RESULT' if a timeout occurs or a connection error prevents retrieving the result.

    Raises:
        ValueError: If no test orchestrator URL is provided.
    """
    if not test_orchestrator_url:
        raise ValueError(f"No URL provided for test ID '{test_id}'.")

    start_time: float = time.time()
    test_result: str = NO_RESULT

    while True:
        try:
            response = requests.get(f"{test_orchestrator_url}/{test_id}/conclusion", timeout=10)
            if response.status_code == 200:
                test_result = response.text.strip().replace('"', '')
        except requests.RequestException as e:
            logger.warning(f"Failed to retrieve result for test ID '{test_id}': {e}")
            return NO_RESULT

        if test_result != NO_RESULT:
            break

        elapsed_time: float = (time.time() - start_time) / 60
        if elapsed_time > timeout_minutes:
            logger.warning(f"Timeout reached while waiting for test case '{test_id}'.")
            return NO_RESULT

        time.sleep(sleep_interval)

    logger.info(f"Test case '{test_id}' ended with result: {test_result}")
    return test_result

def start_multiple_test_cases(
        test_cases: List[str],
        test_orchestrator_url: str,
        run_sequential: bool = False,
        timeout_minutes: int = 5,
        sleep_interval_in_seconds: int = 60
) -> Dict[str, str]:
    """
    Starts multiple test cases and collects their results.

    Args:
        test_cases (List[str]): A list of test case names to execute.
        test_orchestrator_url (str): The base URL of the test orchestrator.
        run_sequential (bool): If True, waits for each test to complete before starting the next.
                               If False, starts all tests first and then waits for results.
        timeout_minutes (int): Maximum time to wait for each test result in minutes (default: 5).
        sleep_interval_in_seconds (int): Time to wait between polling attempts in seconds (default: 60).

    Returns:
        Dict[str, str]: A dictionary mapping test IDs to their results.

    Raises:
        ValueError: If no test cases or no test orchestrator URL is provided.
        ConnectionError: If a test case fails to start.
    """
    if not test_cases:
        raise ValueError("No test cases provided.")
    if not test_orchestrator_url:
        raise ValueError("No test orchestrator URL provided.")

    test_results: Dict[str, str] = {}
    test_ids: List[str] = []

    for test_case in test_cases:
        test_id = start_test_case(test_case, test_orchestrator_url)
        test_ids.append(test_id)
        if run_sequential:
            result = wait_until_test_case_ends(test_id, test_orchestrator_url, timeout_minutes, sleep_interval=sleep_interval_in_seconds)
            test_results[test_id] = result

    if not run_sequential:
        for test_id in test_ids:
            result = wait_until_test_case_ends(test_id, test_orchestrator_url, timeout_minutes, sleep_interval=sleep_interval_in_seconds)
            test_results[test_id] = result

    return test_results
