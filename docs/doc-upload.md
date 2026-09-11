# Documentation upload

Teams document next to their code, and a pipeline hands that documentation to the **jEAP doc service**, which
generates one arc42 site out of it and the architecture model of the system. This module is the step that hands
it over: it packs each documentation set a repository declares into a ZIP and uploads it.

It is the step after [Documentation validation](doc-validation.md), and it is deliberately a separate one: the
validation tells a team what is wrong with its documentation, this publishes what is right.

## Calling it

```python
import json

from jeap_pipeline import (UploadProvenance, documentation_sets_from_config,
                           upload_documentation_sets)

with open(configuration_file) as configuration:
    documentation_sets = documentation_sets_from_config(json.load(configuration),
                                                        configuration_file)

outcome = upload_documentation_sets(
    documentation_sets,
    doc_service_url="https://docs.example.ch",
    token_uri="https://auth.example.ch/oauth2/token",
    client_id="orders-doc-pipeline",
    client_secret=client_secret,
    provenance=UploadProvenance(
        source_repository="https://github.com/example-org/orders-docs",
        source_revision=commit,
        source_ref=branch,
        source_timestamp=commit_timestamp,
        build_url=run_url,
        generated_at=now),
    versions={"./docs": "1.0.0-20260911073000"},
    upload_id_seed=f"{repository}/{run_id}/{run_attempt}")

print(outcome.report)
if not outcome.accepted:
    raise SystemExit(1)
```

One token is fetched for all the sets, and **every set is resolved and walked before the first one is sent** -
what it says about itself, and the folder it is in - so a set that cannot say it, or a `path` that is a typo,
fails the run while nothing is published yet.

`outcome` carries `accepted` (the exit code), `report` (the rendered text), `findings` - the findings of every
refused set flattened, each with its code, message, path and line, as the validation carries them - and one
`SetUploadOutcome` per set with the answer of the doc service in it.

## What is uploaded

Every documentation set handed in, in the format it is written in - Markdown pages and the static HTML of a
microsite alike. Which sets a pipeline uploads is the pipeline's decision: it hands in what it means to publish.

The archive holds exactly the files [`collect_documentation_paths`](doc-validation.md) walked, under the names
they have inside the set: the folder inside the archive is the chapter folder the doc service sorts the pages
into, so what was validated is what is uploaded.

## What an upload says about itself

The query parameters are the keys of the documentation configuration, so a pipeline passes its configuration
through instead of translating it - plus what only an upload carries: the version and the
provenance.

| Parameter                                                                    | Where it comes from                                                                                                                   |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `type`, `system`, `component`/`library`, `template`, `source-format`, `site` | The documentation configuration                                                                                                       |
| `location`, `topic`, `label`                                                 | The documentation configuration, for an HTML microsite: the chapter it is embedded in, the slug it is served under and its menu label |
| `version`                                                                    | The version of the component or library the set documents - see below                                                                 |
| `source-repository`, `source-revision`, `source-ref`, `source-timestamp`     | `UploadProvenance`: the commit the documentation was taken from                                                                       |
| `build-url`, `generated-at`                                                  | `UploadProvenance`: the run that uploaded it                                                                                          |

The doc service renders the provenance under every page, so what is sent here is what a reader of the site sees.

**A component's and a library's documentation carries a version, a system's carries none.** Where the version
comes from is the pipeline's business - the project file of the repository, or the `version` at the root of the
documentation configuration, which is sent when the caller resolved none. A set that needs a version and has
none is refused here rather than by the doc service, so the message names the pipeline's own input - and so is
a `versions` entry for a `system-docs` set, which has no version to name. Both are refused **before** the first
upload, as is a folder that is not there, so a run either publishes every set or none.

## Idempotency: the upload id

`uploadId` is the idempotency key of the doc service's API: one id is one upload, and repeating a `PUT` under it
never produces a second documentation set. The rule is therefore that a **retry** repeats the id and a **re-run**
does not, and `upload_id_seed` is what makes that true - the identity of the run, from which the id of each set
is derived:

```python
upload_id_seed=f"{repository}/{run_id}/{run_attempt}"
```

Every attempt of one run sends the same id, a re-run sends a new one. Without a seed each set gets a random id,
which is right for a caller that cannot say which run it is.

**An attempt that repeats an id repeats the whole provenance with it.** The doc service compares everything an
upload says about itself, `generated-at` and `build-url` included, and answers `UPLOAD_ID_CONFLICT` when
anything of it moved - so resolve the `UploadProvenance` once per run rather than per attempt, and never with a
timestamp taken at the moment of sending.

**The same file is sent on every attempt.** The doc service compares the parameters of a repeated upload and not
the bytes, and a ZIP packed twice differs in its entry timestamps - so re-packing between two attempts would
start a second upload under an id that names the first.

## The answers, and what they mean

| Answer                     | What it means                                                                                                                                                                                                          |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `201`                      | The bundle was stored and the set is current. The site publishes it with its next build                                                                                                                                |
| `200`                      | The same upload id had been stored before; nothing changed                                                                                                                                                             |
| `409 UPLOAD_IN_PROGRESS`   | Another attempt of this upload is being received. Repeated after the `Retry-After` it names, each wait clamped to `MAX_RETRY_AFTER_SECONDS`, for `DEFAULT_IN_PROGRESS_ATTEMPTS` waits before the upload is given up on |
| `5xx`, or no answer at all | Retried with the same id and the same file                                                                                                                                                                             |
| Anything else              | Raises, with the `code` of the problem document and what it means for the configuration                                                                                                                                |

A `422` is the one refusal that is about the documentation rather than about the request: the set would not be
published as it is. It is **not** an exception - the findings are an answer, and they land in `outcome.report`
in the same layout the validation prints them in, with `accepted` false and `SetUploadOutcome.structure`
carrying the report. A pipeline therefore prints the findings of an upload without knowing which of the two
endpoints refused the set.

It should not happen after a validation of the same tree: when it does, the two disagree, and the findings are
what says how. The rules a set is held against, and every answer the endpoint gives, are documented with
[the jEAP doc service](https://jeap-admin-ch.github.io/docs/building-blocks/reusable-microservices/jeap-doc-service/).

## What can go wrong, and what it means

| Raised                     | What to do                                                                                                                                         |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DocumentationConfigError` | The documentation configuration is wrong, or a set that needs a version was uploaded without one                                                   |
| `DocumentationPathError`   | The `path` of a set does not exist, or is not a folder                                                                                             |
| `OAuthTokenError`          | No token: the client id and secret pair, or the token endpoint, is not the one the authorization server knows                                      |
| `DocServiceRequestError`   | The doc service refused the request - an unknown parameter (`400`), no permission for that system (`403`), or a set larger than one may be (`413`) |
| `DocServiceError`          | The doc service could not be reached, or answered with a server error three times over                                                             |

## Related

- [Documentation validation](doc-validation.md) - the step before this one
- [Modules](modules.md) - the whole public API
- [The jEAP doc service](https://jeap-admin-ch.github.io/docs/building-blocks/reusable-microservices/jeap-doc-service/) -
  the upload endpoint, its parameters, its answers, and what becomes of a bundle once it is stored
