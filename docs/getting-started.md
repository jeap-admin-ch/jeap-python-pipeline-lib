# Getting started

`jeap-python-pipeline-lib` is published to PyPI as **`jeap-pipeline`** and imported as
**`jeap_pipeline`**. It is a plain Python library — there is no CLI. Pipelines (GitHub Actions,
Jenkins, Tekton) call its functions from small Python steps.

## Install

```bash
pip install jeap-pipeline
```

Requires Python 3.8+. The library depends on `boto3` (AWS calls) and `requests` (HTTP calls to jEAP
services such as the Deployment Log, the Message Contract Service, the Pact Broker and the test
orchestrator).

## Use

Everything in the public API is re-exported from the top-level package, so a single import is enough:

```python
from jeap_pipeline import (
    wait_until_deployments_completed,
    do_can_i_deploy_check,
    start_test_case,
)
```

Example — wait for an ECS rollout to reach the expected image version and fail the pipeline step
otherwise:

```python
from jeap_pipeline import wait_until_deployments_completed, DeploymentFailedError

try:
    wait_until_deployments_completed(
        cluster_name="my-cluster",
        services=["my-service"],
        expected_image_version="1.42.0",
        aws_region="eu-central-2",
    )
except DeploymentFailedError as error:
    # error.failed_deployments holds the per-service status snapshots
    raise
```

See [Modules](modules.md) for the full catalog and [ECS deployment checks](ecs-deployment.md) for the
deployment waiter and failure diagnostics.

## Related

- [Modules](modules.md) — what the library provides, grouped by area.
- [Development](development.md) — building, testing and publishing the library itself.
