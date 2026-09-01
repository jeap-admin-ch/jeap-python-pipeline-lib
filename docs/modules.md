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

## Related

- [Getting started](getting-started.md)
- [ECS deployment checks](ecs-deployment.md)
