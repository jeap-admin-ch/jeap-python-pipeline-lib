# Modules

All public functions and classes are re-exported from the top-level `jeap_pipeline` package. They
group into the following areas.

## ECS deployment (AWS)

See [ECS deployment checks](ecs-deployment.md) for details.

| Symbol | Purpose |
|---|---|
| `wait_until_deployments_completed` | Block until the ECS deployments of the given services run the expected image version, or raise `DeploymentFailedError` / time out. |
| `get_deployment_status` | One-shot deployment state of a single ECS service relative to an expected image version. |
| `get_failure_diagnostics` | Collect structured failure details (stopped tasks, container exit codes, CloudWatch log events) for a failed rollout. |
| `build_cloudwatch_log_stream_url` | Build a CloudWatch console URL pointing at a specific log stream. |
| `wait_until_undeployment_has_finished`, `is_service_undeployed` | Wait for / check that an ECS service is fully undeployed (INACTIVE or absent). |
| `DeploymentStatus`, `DeploymentFailedError`, `DeploymentFailureDiagnostics`, `ServiceFailureDiagnostics`, `StoppedTaskDiagnostics`, `ContainerFailureDiagnostics`, `CloudWatchLogEvent` | Result / error dataclasses. |

## Deployment Log service

Records deployments and undeployments in the jEAP Deployment Log service.

| Symbol | Purpose |
|---|---|
| `create_deployment_json`, `create_undeployment_json` | Build the request payloads. |
| `put_to_deployment_log_service`, `put_deployment_state`, `put_undeployment_state` | Create / update a (un)deployment and its state. |
| `put_artifacts_version` | Record the artifact coordinates and build URL. |
| `get_previous_deployment_on_environment` | Look up the deployment currently on an environment. |
| `create_change_log`, `get_commit_details`, `get_tagged_at` | Assemble the changelog (JIRA keys, commit and tag timestamps). |
| `generate_deployment_id`, `get_actual_timestamp` | Helpers for IDs and ISO-8601 timestamps. |
| `Deployment`, `DeploymentTarget`, `DeploymentUnit`, `ComponentVersion`, `Link`, `ChangeLog` | Model dataclasses. |

## Pact / consumer-driven contract testing

Talk to the Pact Broker from build and deployment pipelines.

| Symbol | Purpose |
|---|---|
| `verify_pact_configuration` | Validate that configured `pactPacticipants` are real service names. |
| `is_pact_enabled_for_service_and_stage`, `is_pact_can_i_deploy_check_enabled` | Evaluate the pipeline's Pact configuration for a service / environment. |
| `get_pacticipant_names` | Resolve the Pact participant name(s) for an application. |
| `do_can_i_deploy_check` | Run a `can-i-deploy` check before deploying. |
| `record_deployment`, `record_undeployment` | Register a (un)deployment of a participant in an environment. |

## Message Contract Service

| Symbol | Purpose |
|---|---|
| `is_message_contract_compatibility_check_enabled` | Whether the compatibility check runs for an environment. |
| `get_app_name_for_message_contract` | Resolve the app name used for message contracts. |
| `get_compatibility`, `record_deployment`, `delete_deployments` (`message_contract_service_operations`) | Query compatibility and record / remove deployments. |

## Business process test orchestrator

Drive [jeap-bptest-orchestrator](https://jeap-admin-ch.github.io/docs/building-blocks/reusable-microservices/jeap-bptest-orchestrator/)
test runs from a pipeline.

| Symbol | Purpose |
|---|---|
| `start_test_case` | Start one test case, return its test id. |
| `wait_until_test_case_ends` | Poll until the test case has a result or the timeout elapses. |
| `start_multiple_test_cases` | Start several test cases (sequential or parallel) and collect the results. |
| `PASS`, `NO_RESULT` | Result constants. |

## Staging, dispatch and change management

| Symbol | Purpose |
|---|---|
| `get_next_deployment_stage` | Compute the next stage from the current stage and the automated-staging configuration. |
| `send_dispatch_event` | Send a GitHub repository dispatch event to trigger a downstream workflow. |
| `create_change_request_in_remedy`, `get_change_request_id_from_response` | Create a change request in Remedy and read its id from the response. |

## Documentation validation (jEAP doc service)

Validate a repository's documentation before it is uploaded - see
[Documentation validation](doc-validation.md) for the checks, the configuration and the finding codes.

| Symbol                                                                                                                                                                                                            | Purpose                                                                                                                                                             |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `validate_documentation_sets`                                                                                                                                                                                     | Validate every documentation set of a repository, content and structure, and render the report a pipeline prints.                                                   |
| `documentation_sets_from_config`                                                                                                                                                                                  | Read a documentation configuration - what the repository documents at its root, its sets under `docs` - into typed sets, applying the rules of the upload contract. |
| `documentation_sets_from_entries`                                                                                                                                                                                 | Read the documentation a build generates - a list under `generated-docs`, every entry naming its own subject - into typed sets, restricted to the formats the caller uploads. |
| `DocumentationSet`                                                                                                                                                                                                | One folder of documentation and what it is; `validation_query_parameters` and `upload_query_parameters` select what each request may send.                          |
| `validate_documentation_content`                                                                                                                                                                                  | The pipeline's responsibility: encoding, CommonMark, front matter allowlist, links that resolve.                                                                    |
| `collect_documentation_paths`                                                                                                                                                                                     | Walk a documentation folder into the relative path tree an upload would carry.                                                                                      |
| `validate_documentation_structure`                                                                                                                                                                                | Ask the doc service whether a path tree would be accepted, with retries on a server error.                                                                          |
| `DocumentationValidationOutcome`, `SetOutcome`, `Finding`, `ContentReport`, `ContentFinding`, `StructureReport`, `StructureFinding`                                                                               | Result dataclasses.                                                                                                                                                 |
| `ContentFindingCode`, `StructureFindingCode`, `ALLOWED_FRONT_MATTER_KEYS`, `CONFIGURATION_ROOT_KEYS`, `DOCUMENTATION_SET_KEYS`, `SUBJECT_KEYS`, `DOCUMENTATION_SETS_KEY`, `GENERATED_DOCUMENTATION_SET_KEYS`, `GENERATED_DOCUMENTATION_SETS_KEY`, `DOCUMENTATION_TYPES`, `SOURCE_FORMATS` | What the checks branch on, and what is allowed.                                                                                                                     |
| `DocumentationConfigError`, `DocumentationPathError`, `DocServiceError`, `DocServiceRequestError`                                                                                                                 | Errors.                                                                                                                                                             |

## Documentation upload (jEAP doc service)

Upload a repository's documentation to the doc service - see [Documentation upload](doc-upload.md) for the
bundle, the idempotency key and the answers.

| Symbol                                                                              | Purpose                                                                                                                        |
|-------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------|
| `upload_documentation_sets`                                                         | Upload the documentation sets of a repository and render the report a pipeline prints.                                         |
| `UploadProvenance`                                                                  | Where an uploaded set comes from: the repository, the commit, the ref, its timestamp, and the run that uploaded it.            |
| `upload_documentation_bundle`                                                       | Send one ZIP with its prepared query parameters and read the answer, with the retries a restart and a concurrent attempt need. |
| `write_documentation_bundle`                                                        | Write the ZIP of one set, holding exactly the walked paths under their set-relative names.                                     |
| `upload_id_of`                                                                      | The idempotency key of a set's upload, derived from the identity of the run so a retry repeats it and a re-run does not.       |
| `format_set_upload_report`                                                          | Render what became of one set as the text a workflow prints.                                                                   |
| `DocumentationUploadOutcome`, `SetUploadOutcome`, `UploadResult`                    | Result dataclasses. The outcome carries `findings`, the refused sets flattened the way a validation flattens its own.          |
| `DEFAULT_UPLOAD_TIMEOUT`, `DEFAULT_IN_PROGRESS_ATTEMPTS`, `MAX_RETRY_AFTER_SECONDS` | The defaults an upload can be given instead, and the cap on a `Retry-After`.                                                   |

## Which branches publish (jEAP doc service)

Decide whether a push publishes the documentation of its repository - see
[Documentation upload](doc-upload.md#which-branches-publish) for the key, the precedence and the pattern syntax.

| Symbol                                                                             | Purpose                                                                                                   |
|------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| `publishes_from`                                                                   | Whether a ref publishes, which rule decided and the sentence to print.                                    |
| `publish_branches_of`                                                              | The branch patterns a repository states at the root of its documentation configuration, if it states any. |
| `branch_matches`                                                                   | Whether a branch name matches one branch glob - `*` stops at a `/`, `**` does not.                        |
| `PublicationDecision`                                                              | What was decided: `publishes`, `branch`, `rule`, `pattern` and `reason`.                                  |
| `PUBLISH_BRANCHES_KEY`, `RULE_DEFAULT_BRANCH`, `RULE_PUBLISH_BRANCHES`, `RULE_TAG` | The configuration key, and the rules a decision names.                                                    |

## OAuth 2.0 tokens

| Symbol                           | Purpose                                                                                                                   |
|----------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| `fetch_client_credentials_token` | Obtain an access token with the client credentials grant, for any jEAP service a pipeline calls with a client of its own. |
| `OAuthTokenError`                | Raised when no token could be obtained.                                                                                   |

## Related

- [Getting started](getting-started.md)
- [ECS deployment checks](ecs-deployment.md)
- [Documentation validation](doc-validation.md)
- [Documentation upload](doc-upload.md)

## AsciiDoc conversion

See [AsciiDoc conversion](doc-conversion.md) for `convert_asciidoc`,
`prepare_documentation_config`, `requires_asciidoc_conversion` and `DocumentationConversionError`.
