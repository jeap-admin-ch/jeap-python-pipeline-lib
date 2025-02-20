from typing import Dict


def get_next_deployment_stage(current_stage: str, automated_staging: Dict[str, str]) -> str:
    """
    Get the next deployment stage based on the current stage and the automated staging configuration.

    Args:
        current_stage (str): The current stage of deployment.
        automated_staging (Dict[str, str]): A dictionary containing the staging configuration.

    Returns:
        str: The next deployment stage if found, otherwise None.
    """
    return automated_staging.get(current_stage, None)
