# Documentation pipeline adapters

The public helpers in `jeap_pipeline` are independent of the CI platform. They neither
read CI environment variables nor exit the process. File/configuration failures raise
`DocumentationConfigError` for the adapter to report.

- `read_documentation_configuration_file(config_file_path)` loads UTF-8 JSON.
- `configured_documentation_sets(configuration, config_file_path, generated)` parses a prepared configuration.
  Set `generated=True` for `generated-docs`, otherwise use the standalone `docs` contract.
- `documentation_versions(sets, version_argument="", project_version=None, generated=False)`
  chooses the configured version, then the explicit input, then a lazily invoked no-argument
  project-version callback. It invokes that callback at most once. System docs need no version;
  generated docs never infer one, including through an explicitly supplied callback. Pass
  `generated=True` for generated sets here as well as to `configured_documentation_sets`.
  By default it reads the literal version of `pom.xml` for committed documentation.
  The result uses path keys for unique paths and `DocumentationSet` keys for shared paths;
  pass it directly to `upload_documentation_sets`. A callback returning no version leaves the
  affected sets out of the result, so upload validation can report the missing version.
- `documentation_pom_version(pom_file_path="pom.xml")` reads the project's own literal version, accepting
  namespaced and plain POMs. Parent inheritance and unresolved Maven properties are rejected.
- `documentation_commit_timestamp(revision)` reads the commit timestamp from the current checkout.
  Annotated tags resolve to their commit; non-commit objects and revision ranges are rejected.
  Git failures include Git's diagnostic message in the configuration error.

Adapters call `prepare_documentation_config` first and pass the same prepared sets to
`validate_documentation_sets` and `upload_documentation_sets`. Validation failure must stop upload.
For standalone docs, `publishes_from` and `publish_branches_of` decide whether to upload, after
validation. The adapter supplies credentials, repository URL, ref, resolved commit, build URL and
an upload ID seed identifying the run attempt. CI-specific summaries and report files remain in
the adapters. Never pass a client secret in process arguments.

Build version generation remains owned by each CI adapter. A caller with custom artifact versioning
should pass the actual artifact version rather than guess it.
