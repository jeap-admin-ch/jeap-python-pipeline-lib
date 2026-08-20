# 📦 Available Modules

The library currently includes the following modules:

| Module Name                           | Description                                                       |
|---------------------------------------|-------------------------------------------------------------------|
| `automated_staging`                   | Utilities to support automated staging processes                  |
| `deployment_log_operations`           | Interface to the Deployment-Log service for recording deployments |
| `ecs_deployment_checker`              | Helper methods for checking the status of ECS deployments         |
| `github_dispatch_event`               | Sends custom dispatch events to GitHub                            |
| `message_contract_service_operations` | Interface to the Message Contract Service                         |
| `pact_operations`                     | Utilities for interacting with a Pact Broker                      |
| `pact_pacticipants`                   | Tools for managing Pact Broker participants                       |
| `remedy_operations`                   | Interface to Remedy for publishing change requests                |

# 📖 Usage

To use these modules, install the package via PyPI or Test PyPI, depending on the version you want to work with (see main repository documentation for installation steps).

## ECS deployment failure diagnostics

Failure details and application logs are collected only through the explicit diagnostics API; the
deployment waiter never prints CloudWatch logs:

```python
from jeap_pipeline import (
    DeploymentFailedError,
    get_failure_diagnostics,
    wait_until_deployments_completed,
)

try:
    wait_until_deployments_completed(
        cluster_name, services, expected_image_version, aws_region
    )
except DeploymentFailedError as error:
    diagnostics = get_failure_diagnostics(
        cluster_name=cluster_name,
        services=services,
        expected_image_version=expected_image_version,
        aws_region=aws_region,
        deployment_statuses=error.failed_deployments,
        include_logs=True,
        log_event_limit=100,
    )
    raise
```

The result contains structured service, deployment status, stopped-task, container and CloudWatch
log-event dataclasses. Errors from individual AWS lookups are retained in the corresponding
`errors` list, so missing log permissions do not hide ECS task failure information. Passing the
status snapshots from `DeploymentFailedError` keeps diagnostics tied to the failed task definition
even if ECS has already rolled the service back.

`DeploymentFailedError` can preserve only rollout failures observed during polling. If ECS marks a
rollout failed and completes its rollback entirely between two polls, the waiter may observe only
the previous image again and eventually report a timeout instead.

Each container diagnostic indicates through `has_awslogs_configuration` whether its task-definition
entry uses the `awslogs` driver. Runtime-injected containers without such an entry remain available
for exit-code and failure-reason analysis but do not report missing CloudWatch configuration as an
error. When region, log group and log stream are known, `cloudwatch_log_url` links directly to that
stream in the AWS console, regardless of whether log events were requested.
