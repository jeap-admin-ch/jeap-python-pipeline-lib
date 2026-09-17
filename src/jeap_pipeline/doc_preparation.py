"""Normalize pipeline inputs before the upload contract sees them."""

import copy
import re
from pathlib import Path

from .doc_conversion import convert_asciidoc
from .doc_service_operations import (DocumentationConfigError, documentation_sets_from_config,
                                     documentation_sets_from_entries)


def requires_asciidoc_conversion(configuration: dict, *, config_kind: str = "documentation") -> bool:
    """Validate pipeline configuration and say whether conversion tools are needed."""
    _, conversions = _normalize(configuration, _entries_key(config_kind))
    return bool(conversions)


def prepare_documentation_config(configuration: dict, output_directory: str,
                                  working_directory: str = ".", node: str = "node",
                                  pandoc: str = "pandoc", *, config_kind: str = "documentation") -> dict:
    """Convert AsciiDoc entries and return configuration for existing validation and upload.

    Output is relative to the checkout and must be empty. The returned paths are also relative
    to the checkout, not to the file where the caller saves the configuration. The input object
    is never modified. Ordinary Markdown and HTML entries pass through unchanged.
    Use config_kind="build" for generated-docs entries, each naming its own subject.
    Build configuration outside generated-docs is preserved without interpreting it.
    """
    key = _entries_key(config_kind)
    prepared, conversions = _normalize(configuration, key)
    root = Path(working_directory).resolve()
    output = (root / output_directory).resolve()
    if not output.is_relative_to(root) or output == root:
        raise DocumentationConfigError("Conversion output must be a directory inside the checkout.")
    for entry in configuration[key]:
        source = (root / entry["path"]).resolve()
        if not source.is_relative_to(root):
            raise DocumentationConfigError(f"Documentation path leaves the checkout: {entry['path']}")
        if source == output or source in output.parents or output in source.parents:
            raise DocumentationConfigError("Conversion output must not overlap a documentation input.")
    if conversions and output.exists() and any(output.iterdir()):
        raise DocumentationConfigError(f"Conversion output must be empty: {output_directory}")
    for index, entry in conversions:
        set_root = output / f"set-{index}"
        convert_asciidoc(str(root / entry["path"]), str(set_root / entry["location"]),
                         entry.get("entry", "all-docs.adoc"), node, pandoc)
        prepared[key][index]["path"] = set_root.relative_to(root).as_posix()
    return prepared


def _entries_key(config_kind):
    if config_kind not in ("documentation", "build"):
        raise DocumentationConfigError("config_kind must be 'documentation' or 'build'.")
    return "generated-docs" if config_kind == "build" else "docs"


def _normalize(configuration, key):
    if not isinstance(configuration, dict):
        raise DocumentationConfigError("The pipeline configuration must be an object.")
    prepared = copy.deepcopy(configuration)
    conversions = []
    if isinstance(prepared.get(key), list):
        for index, entry in enumerate(prepared[key]):
            if not isinstance(entry, dict) or entry.get("source-format") != "asciidoc":
                continue
            original = copy.deepcopy(entry)
            location = entry.pop("location", None)
            if not isinstance(location, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", location):
                raise DocumentationConfigError(f"{key}[{index}]: AsciiDoc requires a chapter slug in 'location'.")
            entry_file = entry.pop("entry", "all-docs.adoc")
            if (not isinstance(entry_file, str) or not entry_file or "\\" in entry_file
                    or Path(entry_file).is_absolute() or ".." in Path(entry_file).parts):
                raise DocumentationConfigError(f"{key}[{index}]: 'entry' must be a relative file inside 'path'.")
            entry["source-format"] = "markdown"
            conversions.append((index, original))
    # The existing parser remains the authority for subjects, unknown keys and the wire formats.
    sets = (documentation_sets_from_entries(prepared.get(key)) if key == "generated-docs"
            else documentation_sets_from_config(prepared))
    seen = {}
    for index, document in enumerate(sets):
        identity = (document.site, document.type, document.system, document.component,
                    document.library, document.template, document.source_format,
                    document.location, document.topic)
        if identity in seen:
            raise DocumentationConfigError(
                f"{key}[{seen[identity]}] and {key}[{index}] publish the same documentation set after "
                "conversion. Uploads replace the whole set, not individual chapters.")
        seen[identity] = index
    return prepared, conversions
