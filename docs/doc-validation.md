# Documentation validation

AsciiDoc inputs are [converted first](doc-conversion.md). The validator receives the prepared
Markdown configuration, never the original AsciiDoc entry.

Teams document next to their code: a repository holds Markdown under `docs/`, a pipeline uploads it to the
**jEAP doc service**, and the doc service generates one arc42 site out of the uploaded documentation and the
architecture model. The generator runs centrally, so a page that cannot be published would otherwise fail a
site build twenty minutes later, naming a route rather than a file, far away from the person who wrote it.

This module is what prevents that: it validates a repository's documentation **before anything is uploaded**.

## Three responsibilities, and who carries which

| Responsibility | Where                 | What it checks                                                                                                                                                                                      |
|----------------|-----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Content**    | here, in the pipeline | The Markdown itself: it is UTF-8, it parses as CommonMark, its front matter is a mapping whose keys are allowed, and every relative link and image resolves to a file in the same documentation set |
| **Diagrams**   | here, in the pipeline | That the image of every diagram was exported after the diagram was last edited                                                                                                                      |
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

One token is fetched for all the sets, and every check always runs: a structural problem does not hide the
content problems, and the other way round, because a validation reporting one thing at a time would cost a push
per mistake.

A pipeline that checks out **shallowly** passes `deepen_diagram_history=True`, which lets the diagram check
fetch the history it needs to date a diagram - see [The diagram checks](#the-diagram-checks).

`outcome` carries three things a pipeline needs: `accepted` (the exit code), `report` (the rendered text) and
`findings` - the reports flattened into one list, each finding with its `location` (`diagrams`, `content` or
`structure`), code, message, path and line, so a pipeline can report each one on the file and the line it is
about. `Finding.repository_path` prefixes the set's own folder, so the path is the one the repository sees.

## The documentation configuration

A repository says **what it documents** once, at the root, and lists its **documentation sets** under `docs` -
one folder each. The keys are the query parameters of the doc service's upload endpoint, so a pipeline passes
its configuration through instead of translating it.

Where that configuration lives is the pipeline's business: it reads the file and hands the parsed JSON to
`documentation_sets_from_config`, which applies the rules below and gives back typed documentation sets.
Documentation a build generates is declared in the pipeline configuration of the build instead and read with
`documentation_sets_from_entries` - see [Documentation upload](doc-upload.md#documentation-a-build-generates);
the checks of a set are the same ones.

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

## The diagram checks

These checks apply to committed Markdown and AsciiDoc documentation. HTML microsites retain all
their assets and do not use inferred source/image pairing: their permitted asset types are open-ended,
so `overview.html`, `overview.js` or a font next to `overview.svg` must not be dropped as editor source.
When calling collection/pairing helpers directly for a microsite, pass `source_format="html"`.

During AsciiDoc conversion, referenced exported images are checked **before any output is written**,
using the original files and Git paths. The converter retains all input dependencies, including
PlantUML sources and includes. An unused SVG beside a source-rendered PlantUML diagram is not dated;
an SVG actually referenced by the document still receives the freshness check.
`prepare_documentation_config(..., deepen_diagram_history=True)` permits fetching missing history.
Entries under `generated-docs` do not undergo this history check: their source is build
output rather than committed documentation. Direct `convert_asciidoc` callers use the same default
check; `check_committed_diagrams=False` explicitly selects generated input.

A diagram is **two files committed side by side in one folder**: the editable source the author works in,
`images/overview.drawio`, and the image exported from it, `images/overview.svg`, which is what the page embeds.
Nothing renders the diagram in the pipeline - that was the decision, so that the picture is already visible in
the preview of a Markdown editor and the convention holds for every diagram tool.

The price of exporting by hand is that it can be forgotten, and that failure is silent: the source is committed
changed, the image stays as it was, and the published page goes on showing last month's picture with nobody the
wiser. So the sources are **left out of the upload** - a `.drawio` is not an extension the doc service
publishes, and an editor file is nothing a reader could open - and the pair is **dated**.

| Code                        | What it means                                                                                             |
|-----------------------------|-----------------------------------------------------------------------------------------------------------|
| `STALE_DIAGRAM_IMAGE`       | The source was committed after its image was exported. Open it, export it over the image, commit both    |
| `UNDATABLE_DIAGRAM_HISTORY` | The checkout cannot date the diagrams - it is shallow, or not a git checkout at all. A set-level finding |

### Which file is whose source

A file is the source of an image when, **in the same folder**, there is an image file whose stem it extends -
its name is `<image-stem>.<anything>` - and its own extension is not one the doc service publishes
(`md png jpg jpeg gif webp avif svg pdf txt csv json yaml yml`):

| In one folder                      | Verdict                                                 |
|------------------------------------|---------------------------------------------------------|
| `overview.svg` + `overview.drawio` | `overview.drawio` is the source                         |
| `flow.png` + `flow.drawio.xml`     | `flow.drawio.xml` is the source                         |
| `report.svg` + `report.pdf`        | not a pair - a `.pdf` is published, so it is an asset   |
| `diagram.svg` + `diagram.png`      | not a pair - both are published                         |

The rule is about the name and not about a list of known diagram tools on purpose: hand-exported images were
chosen precisely so that the convention holds for any editor, and an allowlist of tools would need a release of
this library for every new one. Requiring the companion to be an image, and the candidate to be something the
doc service would refuse anyway, is what keeps the rule from swallowing a real asset. When several images could
claim one source the most specific wins: with `flow.svg` and `flow.detail.svg` both present,
`flow.detail.drawio` belongs to `flow.detail.svg`.

### Why commit dates, and why a shallow checkout is refused

**Not file modification times.** Git neither stores nor restores mtimes: a checkout writes every file at the
same moment, so in a pipeline all mtimes are equal and their order is whatever order git happened to write them
in. An mtime check would pass by luck. The committer date of the commit that last touched each file is the only
thing about a file's age that survives a clone. Two commits pushed together can share a second, so an equal
date is decided by asking which of the two commits came first in the history.

**A shallow checkout has no dates.** `git log -1 -- <path>` answers with the grafted boundary commit for every
file last touched further back, and that answer cannot be told apart from "really changed there" - every pair
would look exactly as old as its image and the check would quietly stop working. So an answer from the boundary
is treated as no answer: with `deepen_diagram_history=True` the history is fetched in rounds (64, 256, 1024
commits, then all of it) until the diagrams can be dated; without it the set is reported
`UNDATABLE_DIAGRAM_HISTORY`. **A set with no diagram causes no git call at all**, so a repository that
documents without one never pays for history to find that out.

A pair that is **not committed yet** is counted and skipped rather than refused, so the check can be run on a
working tree while a diagram is being added.

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
