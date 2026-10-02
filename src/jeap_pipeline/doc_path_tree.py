"""The path tree of a documentation set.

What the jEAP doc service is told about an upload is where each file sits in the uploaded folder, so
a pipeline that wants to know whether a documentation set would be accepted starts by walking that
folder into a list of relative paths.

The list is otherwise unfiltered: the doc service drops the files nobody wrote - `.DS_Store`,
`__MACOSX/`, `Thumbs.db` and their kind - by name and counts them in its answer, so a second copy of
that list here would be a second thing to keep in step.

The one exception is the **diagram sources**. A diagram is committed as the editable source
(`images/overview.drawio`) plus the image exported from it (`images/overview.svg`), and the source
has to come out before the set is sent: its extension is not one the doc service publishes, so a set
carrying one would be refused, and an editor file is not something a reader could open anyway. That
cannot be left to the doc service, which is why it is the one filter here. See
`doc_diagram_sources` for the pairing rule and for the check that the image was actually
re-exported.
"""

import os
from typing import List

from .doc_diagram_sources import diagram_sources_of

#: Directories never walked into. `.git` is not part of a documentation set, and a `path` pointing
#: at a repository root would otherwise send the whole history to the doc service.
_SKIPPED_DIRECTORIES = frozenset({".git"})


class DocumentationPathError(ValueError):
    """Raised when the configured path of a documentation set cannot be walked."""


def documentation_set_root(path: str, working_directory: str = ".") -> str:
    """
    The folder of a documentation set, relative to what the pipeline checked out.

    Args:
        path (str): The `path` of a documentation configuration entry, relative to the root of the
            repository.
        working_directory (str, optional): What that path is relative to. Defaults to the current
            directory, which in a pipeline is the checkout.

    Returns:
        str: The folder to walk.
    """
    normalized = str(path).replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if working_directory in (".", "", None):
        return normalized or "."
    return f"{working_directory.rstrip('/')}/{normalized}" if normalized else working_directory


def collect_documentation_paths(root: str, keep_diagram_sources: bool = False) -> List[str]:
    """
    List every file below `root` as a relative path, the way an upload would carry it.

    Paths use forward slashes on every platform, are relative to `root`, and are sorted, so two runs
    over one folder produce the same list and a report over it is comparable.

    Symbolic links are skipped, files and directories alike: a link is not a file an upload carries,
    and following one leaves the documentation set.

    Diagram sources are left out, because an upload does not carry them - see
    `doc_diagram_sources.diagram_sources_of` for which files those are.

    Args:
        root (str): The folder of the documentation set - the `path` of a documentation
            configuration entry.
        keep_diagram_sources (bool, optional): Whether to keep the diagram sources in the list.
            Defaults to `False`, the list an upload sends. The diagram check needs them, since they
            are what it is about.

    Raises:
        DocumentationPathError: If `root` does not exist or is not a directory. A typo in the
            configuration is a configuration error, not an empty documentation set.

    Returns:
        list[str]: The relative paths of the files below `root`, sorted.
    """
    if not os.path.exists(root):
        raise DocumentationPathError(
            f"The documentation folder '{root}' does not exist. It is the 'path' of a "
            f"documentation configuration entry, relative to the root of the repository.")
    if not os.path.isdir(root):
        raise DocumentationPathError(
            f"The documentation path '{root}' is not a folder. A documentation set is a folder of "
            f"files, and 'path' names that folder.")

    paths = []
    for directory, subdirectories, file_names in os.walk(root):
        subdirectories[:] = [subdirectory for subdirectory in subdirectories
                             if subdirectory not in _SKIPPED_DIRECTORIES
                             and not os.path.islink(os.path.join(directory, subdirectory))]
        for file_name in file_names:
            absolute = os.path.join(directory, file_name)
            if os.path.islink(absolute):
                continue
            paths.append(os.path.relpath(absolute, root).replace(os.sep, "/"))

    paths = sorted(paths)
    if keep_diagram_sources:
        return paths
    sources = set(diagram_sources_of(paths))
    return [path for path in paths if path not in sources]
