from typing import Set, List

def is_pact_can_i_deploy_check_enabled(environment: str, pact_can_i_deploy_check_environments: List[str]) -> bool:
    """
    Check if the 'can-i-deploy' check is enabled for a given environment.

    This function determines if the 'can-i-deploy' check is enabled for the specified environment
    by checking if the environment is listed in the provided list of environments where the check is enabled.

    Args:
        environment (str): The environment to check.
        pact_can_i_deploy_check_environments (List[str]): A list of environments where the 'can-i-deploy' check is enabled.

    Returns:
        bool: True if the 'can-i-deploy' check is enabled for the specified environment, False otherwise.
    """
    return environment in pact_can_i_deploy_check_environments


def is_pact_enabled_for_service_and_stage(current_stage: str, service_name: str, pact_environments: List[str],
                                          is_pact_pacticipant: bool, pact_pacticipants: List[str]) -> bool:
    """
    Check if Pact is enabled for the given service and environment.

    Args:
        current_stage (str): The environment to check.
        service_name (str): The name of the service.
        pact_environments (List[str]): List of environments for which Pact integration is enabled.
        is_pact_pacticipant (bool): Flag indicating if the app is a Pact participant.
        pact_pacticipants (List[str]): List of Pact participants in a project with multiple deployables.

    Returns:
        bool: True if can-i-deploy check is enabled, False otherwise.
    """
    if current_stage in pact_environments:
        if is_pact_pacticipant or service_name in pact_pacticipants:
            return True
    return False


def verify_pact_configuration(pact_pacticipants: List[str], is_pact_pacticipant: bool, services: List[str]) -> None:
    """
    Verifies the Pact configuration by checking if the provided pactPacticipants are valid service names.

    Args:
        pact_pacticipants (List[str]): A list of pactPacticipants to verify.
        is_pact_pacticipant (bool): A flag indicating if the current service is a pactPacticipant.
        services (List[str]): A list of valid service names.

    Raises:
        ValueError: If any pactPacticipants are not valid service names.
    """
    if not pact_pacticipants:
        print("No list of specific pactPacticipants defined. Skipping Pact configuration verification.")
        return

    if is_pact_pacticipant:
        print("pactPacticipant:true is set at the same time as pactPacticipants. Please remove pactPacticipants - "
              "pactPacticipant:true takes precedence!")
        return

    pacticipant_app_name_set: Set[str] = set(pact_pacticipants)
    service_name_set: Set[str] = set(services)

    print(f"Service Names: {service_name_set}")
    print(f"Pacticipant App Names: {pacticipant_app_name_set}")

    pacticipant_names_that_are_not_valid_services = pacticipant_app_name_set - service_name_set
    if pacticipant_names_that_are_not_valid_services:
        msg = f"""
            Some pactPacticipants are not valid service names: {pacticipant_names_that_are_not_valid_services}
            Please check the pactPacticipants configuration in the pipeline configuration, and make sure
            that the list of pactPacticipants (pactPacticipants: {pacticipant_app_name_set}) only contain valid service names (valid app names are: {service_name_set}).
            Simply setting pactPacticipant:true is usually the better configuration option than providing a list of pactPacticipants.
        """
        raise ValueError(msg)
    else:
        print("All pactPacticipants are valid service names.")
