# Documentation validation

Teams document next to their code: a repository holds Markdown under `docs/`, a pipeline uploads it to the
**jEAP doc service**, and the doc service generates one arc42 site out of the uploaded documentation and the
architecture model. The generator runs centrally, so a page that cannot be published would otherwise fail a
site build twenty minutes later, naming a route rather than a file, far away from the person who wrote it.

This module is what prevents that: it validates a repository's documentation **before anything is uploaded**.

## Two responsibilities, and who carries which

| Responsibility | Where                 | What it checks                                                                                                                                                                                      |
|----------------|-----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Content**    | here, in the pipeline | The Markdown itself: it is UTF-8, it parses as CommonMark, its front matter is a mapping whose keys are allowed, and every relative link and image resolves to a file in the same documentation set |
| **Structure**  | in the doc service    | The path tree against the structure template: which chapter folders exist, which extensions they take, and which names the generator writes itself                                                  |

The structure is not checked here on purpose. The rules belong to the structure template - arc42 today - which
lives in [the jEAP doc service](https://jeap-admin-ch.github.io/docs/building-blocks/reusable-microservices/jeap-doc-service/), and a second implementation of them in every pipeline would be a second
thing to keep in step. The doc service answers `POST /api/uploads/docs/validation` with a finding per problem, and this
module prints what it is told.

## Calling it

```python
import json

from jeap_pipeline import documentation_sets_from_config, validate_documentation_sets

with open(configuration_file) as configuration:
    documentation_sets = documentation_sets_from_config(json.load(configuration),
                                                        configuration_file)

outcome = validate_documentation_sets(
    documentation_sets,
    doc_service_url="https://docs.example.ch",
    token_uri="https://auth.example.ch/oauth2/token",
    client_id="orders-doc-pipeline",
    client_secret=client_secret)

print(outcome.report)
if not outcome.accepted:
    raise SystemExit(1)
```

One token is fetched for all the sets, and both checks always run: a structural problem does not hide the
content problems, and the other way round, because a validation reporting one thing at a time would cost a push
per mistake.

`outcome` carries three things a pipeline needs: `accepted` (the exit code), `report` (the rendered text) and
`findings` - the two reports flattened into one list, each finding with its code, message, path and line, so a
pipeline can report each one on the file and the line it is about. `Finding.repository_path` prefixes the set's
own folder, so the path is the one the repository sees.

## The documentation configuration

A repository says **what it documents** once, at the root, and lists its **documentation sets** under `docs` -
one folder each. The keys are the query parameters of the doc service's upload endpoint, so a pipeline passes
its configuration through instead of translating it.

Where that configuration lives is the pipeline's business: it reads the file and hands the parsed JSON to
`documentation_sets_from_config`, which applies the rules below and gives back typed documentation sets.

```json
{
  "system": "orders",
  "component": "foo-bar-scs",
  "docs": [
    {
      "path": "./docs",
      "type": "component-docs",
      "template": "arc42",
      "source-format": "markdown"
    },
    {
      "path": "./html-docs/configuration-reference",
      "type": "component-docs",
      "template": "arc42",
      "source-format": "html",
      "location": "8-crosscutting-concepts",
      "topic": "configuration-reference",
      "label": "Configuration Reference"
    }
  ]
}
```

**At the root - what the repository is.** Said once, and holding for every set in it, so the two sets above
cannot drift apart about which component they document.

| Key         | Required             |                                                                                                 |
|-------------|----------------------|-------------------------------------------------------------------------------------------------|
| `system`    | yes                  | The system the documentation belongs to. The pipeline's client needs the write role for it      |
| `component` | for `component-docs` | The component the documentation is about                                                        |
| `library`   | for `library-docs`   | The library the documentation is about                                                          |
| `version`   | no                   | The version of a component or library. Part of an upload, not of a validation                   |
| `site`      | no                   | The documentation site the documentation belongs to, when the instance configures more than one |
| `docs`      | yes                  | The documentation sets, at least one                                                            |

A root naming **both** a `component` and a `library` is refused: every set inherits what the root says, and a
component's documentation may not name a library or the other way round.

**Per set - what that folder is.**

| Key             | Required   |                                                                                                       |
|-----------------|------------|-------------------------------------------------------------------------------------------------------|
| `path`          | yes        | The folder of the set, relative to the root of the repository. Everything below it belongs to the set |
| `type`          | yes        | `system-docs`, `component-docs` or `library-docs`                                                     |
| `template`      | yes        | The structure template the folders follow - `arc42`                                                   |
| `source-format` | yes        | `markdown` or `html`                                                                                  |
| `location`      | for `html` | The chapter the microsite is embedded in                                                              |
| `topic`         | for `html` | The slug the microsite is served under                                                                |
| `label`         | for `html` | The menu label of the microsite                                                                       |

Every value is a JSON **string**, quotes included - a number would otherwise reach the doc service stringified
and come back as a refusal about a system nobody named. `system`, `component`, `library`, `template`,
`location`, `topic` and `site` are **slugs**: lower case letters, digits and single hyphens. An **unknown key
is rejected**, not ignored - the doc service rejects an unknown upload parameter, and a pipeline that quietly
ignored a misspelled `source-fomat` would be the one place in the chain where a typo is forgiven. A key
written in the wrong half is not reported as unknown but as misplaced, naming where it belongs.

**A validation sends only what the structure depends on.** `version`, `site`, `label` and the provenance of an
upload are refused by the validation endpoint: a path tree does not depend on a commit hash, and an endpoint
that demanded one to answer a structural question would be answering a different one.

## The content checks

Only `.md` files are read; every other file of a set is a link target. A set whose `source-format` is `html` is
not content-checked at all - a microsite is published as it is, in an iframe.

| Code                         | What it means                                                                                  |
|------------------------------|------------------------------------------------------------------------------------------------|
| `INVALID_ENCODING`           | The file is not valid UTF-8, or carries a NUL byte                                             |
| `MALFORMED_MARKDOWN`         | The file cannot be parsed as CommonMark at all                                                 |
| `MALFORMED_FRONT_MATTER`     | The `---` block is never closed, is not valid YAML, carries one key twice, or is not a mapping |
| `FORBIDDEN_FRONT_MATTER_KEY` | A front matter key outside the allowlist                                                       |
| `DEAD_LINK`                  | A relative link or image target that resolves to no file in the set                            |
| `LINK_WITHOUT_EXTENSION`     | A relative link to a page written without its `.md`                                            |
| `LINK_OUT_OF_SET`            | A relative target that climbs out of the documentation folder                                  |

### The front matter allowlist

`title`, `description`, `sidebar_label`, `tags`, `keywords` - everything a page legitimately says about itself.
Everything else is a finding, and `slug` is the one worth spelling out: front matter can change a document's
URL, so an uploaded page could otherwise take over a route the doc service generates. The site is built with
`onDuplicateRoutes: 'throw'`, so that fails the build of the whole part rather than the page. A page's
identity, its URL and its place in the navigation come from the folder it sits in and from what the doc service
writes beside it.

### Links

A relative Markdown link between two pages of a repository keeps working once they are published: the site
generator resolves a relative `.md` link to the target's permalink. So the reverse holds too - a link that
resolves to no file in the set resolves to nothing in the published site either, and two mistakes fall out of
this check for free:

- a link written **without the extension** (`[design](../5-building-block-view/design)`) resolves nowhere and
  fails the site build;
- a link to a **generated page** is a `DEAD_LINK`, because a generated page is not a file in the repository.
  Link one from the site instead, with an absolute path.

### What is deliberately not checked

|                                      |                                                                                                                               |
|--------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| `http(s)` and `mailto` links         | A link checker that reaches the internet makes a build flaky, and a documentation build is not a monitor                      |
| Anchors (`#a-heading`)               | A heading can come from the generated half of the same chapter, so an anchor a repository cannot see is not a mistake it made |
| Site-absolute links (`/systems/...`) | They resolve against the published site, which a pipeline does not have                                                       |
| Missing front matter                 | Not an error: the site derives a page's title from its first heading                                                          |

## What can go wrong, and what it means

| Raised                     | What to do                                                                                                                                                                                                    |
|----------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `DocumentationConfigError` | The documentation configuration is wrong. The message names the source and, for a set, its index under `docs`                                                                                                 |
| `DocumentationPathError`   | The `path` of a set does not exist, or is not a folder. A typo in the configuration, not an empty documentation set                                                                                           |
| `OAuthTokenError`          | No token: the client id and secret pair, or the token endpoint, is not the one the authorization server knows. An authorization server that answers with a server error or cannot be reached is retried first |
| `DocServiceRequestError`   | The doc service refused the request itself - an unknown parameter (`400`), no permission for that system (`403`), or more paths than one validation may carry (`413`)                                         |
| `DocServiceError`          | The doc service could not be reached, or answered with a server error three times over. A restart is retried first                                                                                            |

A `422` from the doc service is **not** an exception: findings are the answer the endpoint exists to give, and
they arrive in `outcome.report` and `outcome.findings`.

## Related

- [Documentation upload](doc-upload.md) - the step after this one
- [Modules](modules.md) - the whole public API
- [The jEAP doc service](https://jeap-admin-ch.github.io/docs/building-blocks/reusable-microservices/jeap-doc-service/) -
  the structural rules an upload is validated against, and the endpoint that answers them
