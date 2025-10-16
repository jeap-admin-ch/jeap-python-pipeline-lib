# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Note: Please keep [publiccode.yml](publiccode.yml) in sinc with this file.

## [0.14.3] - 2025-10-16

### Fixed

- Third party license markdown file is no longer empty

## [0.14.2] - 2025-10-16

### Fixed

- Third party license file generation now includes all dependencies again

## [0.14.1] - 2025-10-16

### Fixed

- Correct timezone handling in deployment_log_operations.py

## [0.14.0] - 2025-10-08

### Changed

- record_undeployment in pact_operations module does not throw an exception if the pacticipant is already undeployed.

## [0.13.0] - 2025-09-18

### Changed

- Removed OpenAPI upload operations

## [0.12.0] - 2025-08-13

### Added

- Added ecs_undeployment_checker module.
- Added pact undeployment in pact_operations module.
- Added delete deployments in message_contract_service_operations module.
- Added Undeployment model and undeploy method in deployment_log_operations module.

## [0.11.0] - 2025-07-29

### Changed

- Remove system name API path fragment when posting OpenAPI specs to the archrepo service
- Remove system name parameter in post_openapi_spec_to_archrepo_service
- Pinned requirements to specific versions

## [0.10.0] - 2025-06-26

### Added

- Set deployment_types = {"CODE"} in deploymentlog request dto

## [0.9.0] - 2025-06-17

### Added

- Added `test_orchestrator` module.

## [0.8.0] - 2025-05-22

### Added

- Added `remedy_operations` module.

## [0.7.0] - 2025-05-08

### Added

- Added `archrepo_operations` module.

## [0.6.0] - 2025-05-07

### Added

- Added readyForDeploy check in `deployment_log_operations`

## [0.4.0] - 2025-03-14

### Added

- Added `deployment_log_model` module.
- Added `deployment_log_operations` module.

## [0.3.4] - 2025-02-20

### Changed

- The parameter `services` is passed for the `send_repository_dispatch_event` function as List[str] instead of a comma seperated list.

## [0.3.3] - 2025-02-19

### Changed

- Removed interval configuration from PACT record-deployment

### Added

- Automated staging module

## [0.3.2] - 2025-02-19

### Changed

- Used typification in current modules.

## [0.3.1] - 2025-02-19

### Fixed

- Use '--environment' instead of '--to-environment' for PACT record-deployment

## [0.3.0] - 2025-02-13

### Added

- Added PACT modules. 

## [0.2.0] - 2025-01-31

### Added

- Added module ecs_deployment_checker and github_dispatch_event.

## [0.1.3] - 2025-01-28

### Added

- Added automated license check and filled requirements.txt.

## [0.1.2] - 2025-01-28

### Changed

- Changed License name to SPDX standard.

## [0.1.1] - 2025-01-28

### Changed

- Changed from MIT License to Apache License 2.0.

### Added

- Added THIRD-PARTY-LICENSES.md and generation in the pipeline. 

## [0.1.0] - 2025-01-27

### Added

- Initial version with Hello jEAP example
