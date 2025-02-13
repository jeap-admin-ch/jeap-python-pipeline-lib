def get_pacticipant_names(app_name, department, pact_pacticipant_name, pact_pacticipant_names, pact_provider_api_names):
    """
    Get the list of Pact participant names for a given application.

    This function determines the Pact participant names based on the provided application name,
    department, and optional Pact participant and provider API names. If the application provides
    different APIs that should be known under different Pact participant names, those names are
    generated and returned.

    Args:
        app_name (str): The name of the application.
        department (str): The department to which the application belongs.
        pact_pacticipant_name (str or None): The specific Pact participant name, if provided.
        pact_pacticipant_names (dict or None): A dictionary mapping application names to Pact participant names.
        pact_provider_api_names (list or None): A list of provider API names for the application.

    Returns:
        list: A list of Pact participant names.
    """
    pact_pacticipant_name = _get_pacticipant_name(app_name, department, pact_pacticipant_name, pact_pacticipant_names)
    if pact_provider_api_names is None:
        return [pact_pacticipant_name]
    else:
        # This app provides different APIs that it wants to make known under different pacticipant names
        pacticipant_per_api_names = []
        for api_name in pact_provider_api_names:
            pacticipant_per_api_names.append(f"{pact_pacticipant_name}_{api_name}")
        return pacticipant_per_api_names


def _get_pacticipant_name(app_name, department, pact_pacticipant_name, pact_pacticipant_names):
    if pact_pacticipant_name is not None:
        return pact_pacticipant_name
    elif pact_pacticipant_names is not None and app_name in pact_pacticipant_names:
        return pact_pacticipant_names[app_name]
    else:
        return f"{department}-{app_name}"
