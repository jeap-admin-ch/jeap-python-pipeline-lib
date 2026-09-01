# jEAP Python Pipeline Library

`jeap-python-pipeline-lib` is a collection of reusable Python modules that standardize CI/CD pipeline
operations in the **jEAP** context — ECS deployment checks on AWS, recording deployments in the jEAP
Deployment Log service, Pact Broker `can-i-deploy` checks, Message Contract Service operations,
business-process test runs, and GitHub / Remedy integrations.

It is published to PyPI as [`jeap-pipeline`](https://pypi.org/project/jeap-pipeline/) and imported as
`jeap_pipeline`. There is no CLI — pipelines call the functions from small Python steps.

```bash
pip install jeap-pipeline
```

## Documentation

| Topic | File |
|---|---|
| Install and first use | [docs/getting-started.md](docs/getting-started.md) |
| Module catalog (what the library provides) | [docs/modules.md](docs/modules.md) |
| ECS deployment checks & failure diagnostics | [docs/ecs-deployment.md](docs/ecs-deployment.md) |
| Building, testing and publishing the library | [docs/development.md](docs/development.md) |

## Changelog

Versioned with [Semantic Versioning](https://semver.org/); changes are recorded in
[CHANGELOG.md](./CHANGELOG.md) ([Keep a Changelog](https://keepachangelog.com/) format). Keep
[publiccode.yml](publiccode.yml) in sync.

## Note

This repository is part of the open source distribution of jEAP. See
[github.com/jeap-admin-ch/jeap](https://github.com/jeap-admin-ch/jeap) for more information.

## License

This repository is Open Source Software licensed under the [Apache License 2.0](./LICENSE).
