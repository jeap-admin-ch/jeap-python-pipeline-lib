# ECS deployment checks

Helpers for pipelines that deploy to AWS ECS: wait for a rollout to converge on the expected image
version, gather structured failure diagnostics when it does not, and wait for an undeployment to
finish.

## Waiting for a deployment

```python
from jeap_pipeline import wait_until_deployments_completed, DeploymentFailedError

try:
    wait_until_deployments_completed(
        cluster_name, services, expected_image_version, aws_region
    )
except DeploymentFailedError as error:
    ...
```

`wait_until_deployments_completed` polls the given services until each one runs
`expected_image_version` as its primary deployment, or raises `DeploymentFailedError` when ECS marks
a rollout as failed, or times out. `get_deployment_status` exposes the same state check for a single
service without polling.

## Failure diagnostics

Failure details and application logs are collected **only** through the explicit diagnostics API; the
deployment waiter never prints CloudWatch logs:

```python
from jeap_pipeline import get_failure_diagnostics, wait_until_deployments_completed, DeploymentFailedError

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

The result is a tree of dataclasses — `DeploymentFailureDiagnostics` → `ServiceFailureDiagnostics` →
`StoppedTaskDiagnostics` / `ContainerFailureDiagnostics` / `CloudWatchLogEvent`. Notes:

- Errors from individual AWS lookups are kept in the corresponding `errors` list, so missing log
  permissions do not hide ECS task-failure information.
- Passing the status snapshots from `DeploymentFailedError` keeps diagnostics tied to the failed task
  definition even if ECS has already rolled the service back.
- `DeploymentFailedError` can only preserve rollout failures observed *during polling*. If ECS marks
  a rollout failed and finishes its rollback entirely between two polls, the waiter may see only the
  previous image again and eventually report a timeout instead.
- Each container diagnostic reports via `has_awslogs_configuration` whether its task-definition entry
  uses the `awslogs` driver. Runtime-injected containers without such an entry are still analysed for
  exit code and failure reason, but do not count as a missing-configuration error.
- When region, log group and log stream are known, `cloudwatch_log_url` links straight to that stream
  in the AWS console, whether or not log events were requested. `build_cloudwatch_log_stream_url`
  builds such a URL directly.

## Waiting for an undeployment

```python
from jeap_pipeline import wait_until_undeployment_has_finished, is_service_undeployed
```

`wait_until_undeployment_has_finished` blocks until an ECS service is fully undeployed — its status
is `INACTIVE` or it no longer exists. `is_service_undeployed` is the one-shot check.

## Related

- [Modules](modules.md)
- [Getting started](getting-started.md)
