# AsciiDoc conversion

Spring Modulith generates AsciiDoc canvases and PlantUML diagrams. Convert them before calling the
existing [validation](doc-validation.md) and [upload](doc-upload.md) APIs. The Doc Service receives
Markdown; it does not need an AsciiDoc source format.

## Configuration

```json
{
  "system": "orders",
  "component": "orders-service",
  "docs": [
    {
      "path": "./docs-src/modulith",
      "type": "component-docs",
      "template": "arc42",
      "source-format": "asciidoc",
      "entry": "all-docs.adoc",
      "location": "5-building-block-view"
    }
  ]
}
```

`entry` defaults to `all-docs.adoc`. `location` is required and names a chapter of the target
template. The service validates the chapter name; the converter only checks that it is a slug.
These options belong to conversion and are removed from the prepared upload descriptor.

```python
from jeap_pipeline import prepare_documentation_config, documentation_sets_from_config

prepared = prepare_documentation_config(configuration, ".jeap-converted-docs")
sets = documentation_sets_from_config(prepared)
# Pass these same sets to validate_documentation_sets, then upload_documentation_sets.
```

The original configuration and input files are untouched. Output must be empty, inside the checkout,
and separate from every input. Prepared paths are relative to the checkout, not to the file holding
the prepared configuration. Version, subject and branch settings are retained.

`requires_asciidoc_conversion(configuration)` checks the configuration before a caller provisions
tools. `convert_asciidoc(input_directory, output_directory, entry="all-docs.adoc")` is the lower-level
API for callers that only need Markdown pages, without upload configuration.

## Tools

Python 3.10+, Node 20+ and Pandoc 3.6.1 are used. Node runs the small Asciidoctor bridge;
conversion policy and output preparation remain in Python. No tool is downloaded by a library call.

The Python wheel includes `asciidoc_tools/package.json` and its lockfile. Copy that directory to a
tool workspace and run `npm ci --ignore-scripts` there. Set `NODE_PATH` to its `node_modules`.
The lockfile pins Asciidoctor.js 3.0.4 and the DocBook converter 3.0.0, including transitive dependencies.

Supply `pandoc` on `PATH`, or pass its executable path as the `pandoc` argument. The GitHub action
installs `pypandoc_binary==1.15`, which provides Pandoc 3.6.1. Pandoc is an external GPL-licensed
executable, not code bundled into this Python library. Asciidoctor.js and its converter are MIT-licensed.

For tests from this checkout:

```shell
npm ci --prefix src/jeap_pipeline/asciidoc_tools --ignore-scripts
export NODE_PATH="$PWD/src/jeap_pipeline/asciidoc_tools/node_modules"
python -m pip install pypandoc_binary==1.15
export PANDOC="$(python -c 'import pypandoc; print(pypandoc.get_pandoc_path())')"
python -m pytest
```

## Output and supported content

- Asciidoctor resolves local includes, including nested includes. Missing files fail conversion.
- Top-level sections become `modulith-<heading>.md` pages. Duplicate names fail rather than overwrite.
- PlantUML macros become fenced `plantuml` blocks. C4 includes are preserved: the Doc Service's
  PlantUML plugin supplies that standard library from the same origin.
- Two-column module canvases with block content become labels and lists. Simple tables stay tables.
  Complex tables with more than two columns are refused. The Doc Service escapes raw HTML, so an
  HTML table would not be a working substitute. Output that still requires raw HTML is refused.
- Section cross-references are rewritten between the split pages. Local images and attachments
  are copied into the chapter's `assets` directory. Link to sections, not to `.adoc` source files.
- Diagram and asset paths are relative to the input root. Symlinks are excluded from the input
  snapshot. Includes run in Asciidoctor's safe mode, with remote includes disabled by default.
- Only `title` front matter is written. The service owns categories, URLs and navigation order.

The generated output still goes through normal content and structural validation. Conversion is
not a replacement for those checks, nor does a successful conversion prove that a diagram renders.

## One upload replaces one set

After conversion, the set is Markdown. Two entries with the same site, subject, template and
format would replace each other, even if they target different chapters. Preparation rejects
that configuration before conversion or upload. Keep one Markdown-producing entry per identity.
This check cannot detect a different repository or workflow publishing over the same set.

## Errors

`DocumentationConfigError` names invalid options or conflicting sets. `DocumentationConversionError`
names missing tools, include/diagram failures and content that cannot be converted. Tool calls have
a two-minute timeout. An incomplete output after a failure must not be uploaded; use an empty staging
directory on the next attempt.
