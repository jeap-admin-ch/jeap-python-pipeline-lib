"""Shared documentation configuration, version selection and checkout metadata.

CI adapters own credentials, reports and build-specific version generation. These helpers
never read platform environment variables and do not terminate the calling process.
"""

import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from .doc_service_operations import (DocumentationConfigError, documentation_sets_from_config,
                                     documentation_sets_from_entries)

VERSIONED_TYPES = ('component-docs', 'library-docs')
GENERATED_DOCUMENTATION_SETS_KEY = 'generated-docs'
GENERATED_SOURCE_FORMATS = frozenset({'html', 'markdown'})
MAVEN_NAMESPACE = {'maven': 'http://maven.apache.org/POM/4.0.0'}


def read_documentation_configuration_file(config_file_path: str) -> dict:
    """Read a pipeline configuration, reporting file and JSON failures as configuration errors."""
    try:
        return json.loads(Path(config_file_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise DocumentationConfigError(
            f"The pipeline configuration '{config_file_path}' does not exist.") from None
    except json.JSONDecodeError as error:
        raise DocumentationConfigError(
            f"The pipeline configuration '{config_file_path}' is not valid JSON: {error}") from None
    except UnicodeDecodeError as error:
        raise DocumentationConfigError(
            f"The pipeline configuration '{config_file_path}' is not valid UTF-8: {error}") from None
    except OSError as error:
        raise DocumentationConfigError(
            f"The pipeline configuration '{config_file_path}' cannot be read: {error}") from None


def configured_documentation_sets(configuration, config_file_path: str, generated: bool):
    """Read committed or generated documentation sets from prepared configuration."""
    if not isinstance(configuration, dict):
        raise DocumentationConfigError(f"{config_file_path} has to hold an object.")
    if generated:
        return documentation_sets_from_entries(
            (configuration or {}).get(GENERATED_DOCUMENTATION_SETS_KEY), config_file_path,
            GENERATED_DOCUMENTATION_SETS_KEY, GENERATED_SOURCE_FORMATS)

    return documentation_sets_from_config(configuration, config_file_path)


def documentation_versions(documentation_sets, version_argument: str = "",
                           project_version=None, generated: bool = False):
    """
    Select configuration, explicit input, then lazily resolved project version, in that order.

    The project file is read only when a set needs a version, so a repository documenting a system
    needs no project file at all - and never for documentation a build generated, where the version
    is the one the build gave the artifact and the workflow is what knows it.

    Versions are keyed by path, or by DocumentationSet when multiple sets share a path.
    Pass the result directly to upload_documentation_sets.
    """
    documentation_sets = list(documentation_sets)
    path_counts = Counter(documentation_set.path for documentation_set in documentation_sets)
    versions = {}
    from_the_project = None
    project_resolved = False
    for documentation_set in documentation_sets:
        if documentation_set.type not in VERSIONED_TYPES:
            continue
        key = (documentation_set if path_counts[documentation_set.path] > 1
               else documentation_set.path)
        if documentation_set.version:
            versions[key] = documentation_set.version
            continue
        if version_argument:
            versions[key] = version_argument
            continue
        if generated:
            continue
        if not project_resolved:
            from_the_project = (project_version or documentation_pom_version)()
            project_resolved = True
        if from_the_project:
            versions[key] = from_the_project
    return versions


def documentation_pom_version(pom_file_path: str = "pom.xml") -> str:
    """
    The `<version>` the project file states for itself.

    Nothing is inherited and nothing is resolved: the parent of a jEAP project is the platform's
    parent, so an inherited version would publish the platform's version as the project's, and
    resolving either that or a property means building the effective model with Maven.
    """
    if not os.path.isfile(pom_file_path):
        raise DocumentationConfigError(
            f"The documentation of a component or a library carries the version of what it "
            f"documents, and there is no '{pom_file_path}' to read it from. State the version in "
            f"the project file, or as 'version' at the root of the documentation configuration.")

    try:
        project = ElementTree.parse(pom_file_path).getroot()
    except (OSError, ElementTree.ParseError) as error:
        raise DocumentationConfigError(f"The project file '{pom_file_path}' cannot be read: {error}") from None

    version = project.find('maven:version', MAVEN_NAMESPACE)
    if version is None:
        version = project.find('version')

    value = (version.text or '').strip() if version is not None else ''
    if not value:
        raise DocumentationConfigError(
            f"The project file '{pom_file_path}' states no version of its own. The version of a "
            f"parent is not inherited here - it is the version of the parent, not of this project "
            f"- so state a <version> in the project file, or 'version' at the root of the "
            f"documentation configuration.")
    if '${' in value:
        raise DocumentationConfigError(
            f"The project file '{pom_file_path}' states its version as '{value}', which is a "
            f"property this workflow does not resolve: resolving one means building the effective "
            f"model with Maven. State a literal <version> in the project file, or 'version' at the "
            f"root of the documentation configuration.")
    return value


def documentation_commit_timestamp(revision: str) -> str:
    """Read a commit's timestamp from the checkout, resolving annotated tags to their commit."""
    try:
        resolved = subprocess.run(['git', 'rev-parse', '--verify', '--end-of-options',
                                   f'{revision}^{{commit}}'],
                                  capture_output=True, text=True, check=True)
        completed = subprocess.run(['git', 'show', '-s', '--format=%cI',
                                    resolved.stdout.strip(), '--'],
                                   capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        detail = str(error)
        if isinstance(error, subprocess.CalledProcessError):
            detail = (error.stderr or '').strip() or detail
        raise DocumentationConfigError(
            f"The commit date of {revision} cannot be read from the checkout: {detail}") from None
    timestamp = completed.stdout.strip()
    if not timestamp or len(timestamp.splitlines()) != 1:
        raise DocumentationConfigError(
            f"The commit date of {revision} is not a single non-empty timestamp.")
    return timestamp
