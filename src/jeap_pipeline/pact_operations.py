import subprocess
from typing import Optional


def do_can_i_deploy_check(pact_pacticipant_name: str,
                          pacticipant_version: str,
                          current_stage: str,
                          retry_attempts: int = 6,
                          retry_interval: int = 5) -> None:
    """
    Check if a Pact participant can be deployed to a specified environment.

    This function runs the `pact-broker can-i-deploy` command to check if a specified version of a Pact participant
    can be deployed to a given environment. Make sure to have the `pact-cli` installed and available in the PATH.
    Ensure that the PACT_BROKER_BASE_URL environment variable is set.

    Args:
        pact_pacticipant_name (str): The name of the Pact participant.
        pacticipant_version (str): The version of the Pact participant.
        current_stage (str): The environment to which the deployment is being checked.
        retry_attempts (int, optional): The number of retry intervals to wait while the status is unknown. Defaults to 6 attempts.
        retry_interval (int, optional): The interval between retries while the status is unknown. Defaults to 5 seconds.

    Raises:
        RuntimeError: If the can-i-deploy check fails.

    Returns:
        None
    """
    command = [
        "pact-broker",
        "can-i-deploy",
        "--pacticipant", pact_pacticipant_name,
        "--version", pacticipant_version,
        "--to-environment", current_stage,
        "--retry-while-unknown", str(retry_attempts),
        "--retry-interval", str(retry_interval)
    ]
    print(f"Running pact-cli command: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    print("Command output:")
    print(result.stdout)

    if result.returncode == 0:
        print(f"Can deploy {pact_pacticipant_name} version {pacticipant_version} to {current_stage}")
    else:
        error_message = f"Cannot deploy {pact_pacticipant_name} version {pacticipant_version} to {current_stage}: {result.stderr}"
        print(error_message)
        raise ValueError(error_message)


def record_deployment(pact_pacticipant_name: str,
                      pacticipant_version: str,
                      current_stage: str) -> None:
    """
    Record the deployment of a Pact participant to a specified environment.

    This function runs the `pact-broker record-deployment` command to record a deployment of a specified version of
    a Pact participant to a given environment.
    Make sure to have the `pact-cli` installed and available in the PATH
    Make sure that the PACT_BROKER_BASE_URL environment is set.

    Args:
        pact_pacticipant_name (str): The name of the Pact participant.
        pacticipant_version (str): The version of the Pact participant.
        current_stage (str): The environment to which the deployment is being checked.

    Raises:
        RuntimeError: If the recording fails.

    Returns:
        None
    """
    command = [
        "pact-broker",
        "record-deployment",
        "--pacticipant", pact_pacticipant_name,
        "--version", pacticipant_version,
        "--environment", current_stage
    ]

    print(f"Running pact-cli command: {' '.join(command)}")
    result = subprocess.run(command, capture_output=True, text=True)
    print("Command output:")
    print(result.stdout)

    if result.returncode == 0:
        print(f"Deployment for {pact_pacticipant_name} version {pacticipant_version} to {current_stage} is recorded")
    else:
        error_message = f"Cannot record deployment of {pact_pacticipant_name} version {pacticipant_version} to {current_stage}: {result.stderr}"
        print(error_message)
        raise RuntimeError(error_message)
