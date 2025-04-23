from typing import List, Dict

def is_message_contract_compatibility_check_enabled(environment: str, message_contract_compatibility_check_environments: List[str]) -> bool:
    """
    Check if the 'message contract compatibility' check is enabled for a given environment.

    This function determines if the 'message contract compatibility' check is enabled for the specified environment
    by checking if the environment is listed in the provided list of environments.

    Args:
        environment (str): The environment to check.
        message_contract_compatibility_check_environments (List[str]): A list of environments where the 'message contract compatibility' check is enabled.

    Returns:
        bool: True if the 'message contract compatibility' check is enabled for the specified environment, False otherwise.
    """
    return environment in message_contract_compatibility_check_environments

def get_app_name_for_message_contract(message_contract_app_name: str, message_contract_app_names: Dict[str, str], app_name: str) -> str:
    """
    Get the app name for the message contract.

    This function returns the app name for the message contract by checking if a custom app name is provided
    or if the app name is in the mapping of app names.

    Args:
        message_contract_app_name (str): The custom app name for the message contract.
        message_contract_app_names (Dict[str, str]): A dictionary of app names and their corresponding message contract app names.
        app_name (str): The app name to check.

    Returns:
        str: The app name for the message contract.
    """
    if message_contract_app_name:
        return message_contract_app_name
    if app_name in message_contract_app_names:
        return message_contract_app_names[app_name]
    return app_name
