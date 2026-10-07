"""The diagram responsibility of validating a documentation set.

A diagram in jEAP documentation is **two files committed side by side in one folder**: the editable
source the author works in, `images/overview.drawio`, and the image exported from it,
`images/overview.svg`, which is what the page embeds. Nothing renders the diagram in the pipeline -
that was the decision, so that the picture is already visible in the preview of a Markdown editor and
the convention works for any diagram tool.

The price of exporting by hand is that it can be forgotten, and that failure is silent: the source is
committed changed, the image stays as it was, and the published page goes on showing last month's
picture with nobody the wiser. This module is the check against it, and it is also what keeps the
sources out of an upload - a `.drawio` is not an extension the doc service publishes, so a set
carrying one would be refused outright.

**Why commit dates and not file modification times.** Git neither stores nor restores mtimes: a
checkout writes every file at the same moment, so in a pipeline all mtimes are equal and their order
is whatever order git happened to write them in. An mtime check would pass by luck. The committer
date of the commit that last touched each file is the only thing about a file's age that survives a
clone.

**Why a shallow checkout is refused rather than passed.** In a shallow clone `git log -1 -- <path>`
answers with the grafted boundary commit for every file that was last touched further back, and that
answer cannot be told apart from "really changed there". Every pair would look exactly as old as its
image and the check would quietly stop working. So an answer that comes from the boundary is treated
as no answer at all: either the history is deepened (`deepen=True`, which fetches only for the sets
that actually have a diagram) or the set is reported as undatable.
"""

import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

#: The extensions the jEAP doc service publishes - its structure template's allowed file extensions.
#: A file carrying one of these is an asset of the documentation in its own right and is never taken
#: for somebody's diagram source, which is what keeps a `report.pdf` next to a `report.svg` safe.
PUBLISHED_EXTENSIONS: FrozenSet[str] = frozenset({
    "md",
    "png", "jpg", "jpeg", "gif", "webp", "avif", "svg",
    "pdf", "txt", "csv", "json", "yaml", "yml",
})

#: The published extensions that are pictures. Only a picture can have been exported from a source.
IMAGE_EXTENSIONS: FrozenSet[str] = frozenset({"svg", "png", "jpg", "jpeg", "gif", "webp", "avif"})

#: Extensions that are never somebody's diagram source, whatever a site publishes: page types, a
#: document a site renders on its own origin, and code a site or a browser runs. The jEAP doc
#: service keeps the same list for the same reason (`MarkdownAssetRules.isNeverAllowed`), because a
#: page or a script beside `overview.svg` is a page, not an editor file. Without it the open-ended
#: rule - anything not published is a candidate source - would delete an `overview.mdx` page and
#: fail the build when only its text changed.
NEVER_SOURCE_EXTENSIONS: FrozenSet[str] = frozenset({
    "md", "mdx",
    "html", "htm", "xhtml", "shtml",
    "js", "mjs", "cjs", "jsx", "ts", "tsx", "css",
    "adoc", "asciidoc",
})

#: How far the history is deepened per round before the whole of it is fetched. A diagram that was
#: touched recently - the usual case - is dated by the first round.
_DEEPEN_ROUNDS: Tuple[int, ...] = (64, 256, 1024)

_GIT_TIMEOUT = 60


class DiagramFindingCode(str, Enum):
    """What is wrong with a diagram of a documentation set."""

    STALE_DIAGRAM_IMAGE = "STALE_DIAGRAM_IMAGE"
    UNDATABLE_DIAGRAM_HISTORY = "UNDATABLE_DIAGRAM_HISTORY"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class DiagramPair:
    """A diagram source and the image exported from it, both relative to the set's folder."""

    source: str
    image: str


@dataclass(frozen=True)
class DiagramFinding:
    """One problem with one diagram. `path` is the source; it is unset for a set-level problem."""

    code: DiagramFindingCode
    message: str
    path: Optional[str] = None


@dataclass(frozen=True)
class DiagramReport:
    """What the diagram check found in a documentation set."""

    pairs_checked: int
    findings: List[DiagramFinding] = field(default_factory=list)
    pairs_uncommitted: int = 0

    @property
    def accepted(self) -> bool:
        """Whether the diagram check found nothing to report."""
        return not self.findings


def diagram_pairs_of(paths: Sequence[str], source_format: str = "markdown") -> List[DiagramPair]:
    """
    Find the diagram source/image pairs in a documentation set.

    A file is the source of an image when, **in the same folder**, there is an image file whose stem
    it extends - its name is `<image-stem>.<anything>` - and its own extension is neither one the
    doc service publishes nor one that is never a source (a page type or browser code, see
    `NEVER_SOURCE_EXTENSIONS`):

    | In one folder                         | Verdict                                              |
    |---------------------------------------|------------------------------------------------------|
    | `overview.svg` + `overview.drawio`    | `overview.drawio` is the source                      |
    | `flow.png` + `flow.drawio.xml`        | `flow.drawio.xml` is the source                      |
    | `report.svg` + `report.pdf`           | not a pair - a `.pdf` is published, so it is an asset |
    | `diagram.svg` + `diagram.png`         | not a pair - both are published                      |
    | `overview.svg` + `overview.mdx`       | not a pair - an MDX page is never an editor file      |

    The rule is about the name and not about a list of known diagram tools on purpose: hand-exported
    images were chosen precisely so that the convention holds for any editor, and an allowlist of
    tools would need a release of this library for every new one. Requiring the companion to be an
    image, and the candidate to be something no site publishes or runs, is what keeps the rule from
    swallowing a real asset or page.

    When several images could claim one source the most specific stem wins: with `flow.svg` and
    `flow.detail.svg` both present, `flow.detail.drawio` belongs to `flow.detail.svg`. **Every
    export format of that stem is paired**, so one `flow.drawio` beside `flow.png` and `flow.svg`
    yields a pair per image and a stale export is found whichever format the page embeds.


    Args:
        paths (Sequence[str]): The relative paths of the set, as `collect_documentation_paths`
            returns them - forward slashes, relative to the set's folder.
        source_format (str): Markdown by default. HTML disables inference to preserve its
            open-ended asset types; AsciiDoc also preserves .adoc and .asciidoc documents.

    Returns:
        List[DiagramPair]: One pair per source found, ordered by source path.
    """
    # HTML microsites have an open-ended asset vocabulary, not Markdown's allowlist.
    # A same-stem HTML/CSS/JS/font file cannot safely be inferred to be editor source.
    if source_format == "html":
        return []
    by_folder: Dict[str, List[str]] = {}
    for path in paths:
        by_folder.setdefault(posix_dirname(path), []).append(path)

    pairs: List[DiagramPair] = []
    for folder, members in by_folder.items():
        images = [member for member in members if _extension_of(member) in IMAGE_EXTENSIONS]
        if not images:
            continue
        for member in members:
            extension = _extension_of(member)
            if (not extension or extension in PUBLISHED_EXTENSIONS
                    or extension in NEVER_SOURCE_EXTENSIONS):
                continue
            for image in _images_claiming(_name_of(member), images):
                pairs.append(DiagramPair(source=member, image=image))

    return sorted(pairs, key=lambda pair: (pair.source, pair.image))


def diagram_sources_of(paths: Sequence[str], source_format: str = "markdown") -> List[str]:
    """
    The diagram sources in a documentation set - the paths an upload leaves out.

    An editor file cannot be opened in a browser, and its extension is not one the doc service
    publishes, so a set that carried one would be refused. The pairing rule is
    `diagram_pairs_of`'s.

    Args:
        paths (Sequence[str]): The relative paths of the set.
        source_format (str): The input format; HTML keeps all assets.

    Returns:
        List[str]: The relative paths of the sources, sorted.
    """
    # One source can have several export formats, so the same source appears in several pairs.
    return sorted({pair.source for pair in diagram_pairs_of(paths, source_format)})


def posix_dirname(path: str) -> str:
    """The folder of a relative set path, `''` for a file at the set's root."""
    separator = path.rfind("/")
    return path[:separator] if separator >= 0 else ""


def check_diagram_sources(root: str,
                          paths: Sequence[str],
                          deepen: bool = False,
                          source_format: str = "markdown",
                          referenced_images: Optional[Sequence[str]] = None) -> DiagramReport:
    """Check diagram freshness, reporting unavailable Git history instead of accepting it.

    `paths` contains unfiltered set-relative paths. `source_format` selects pairing rules;
    `deepen` permits fetching history only when a diagram pair requires it.
    `referenced_images`, when supplied, selects already assigned pairs by image path;
    it never changes the complete tree used to establish the original pairings.
    """
    pairs = diagram_pairs_of(paths, source_format)
    if referenced_images is not None:
        referenced = set(referenced_images)
        pairs = [pair for pair in pairs if pair.image in referenced]
    try:
        return _check_diagram_sources(root, pairs, deepen)
    except (OSError, subprocess.SubprocessError, ValueError, _HistoryError) as error:
        return DiagramReport(pairs_checked=len(pairs), findings=[
            DiagramFinding(DiagramFindingCode.UNDATABLE_DIAGRAM_HISTORY,
                           f"Cannot verify diagram history: {error}")])


class _HistoryError(RuntimeError):
    """Git failed to supply a usable history answer."""


def _check_diagram_sources(root: str, pairs: Sequence[DiagramPair], deepen: bool) -> DiagramReport:
    """
    Check that every diagram of a documentation set was exported after it was last edited.

    Does nothing when the set has no diagram: a repository that documents without one never causes a
    single git call, which is what makes this affordable to run on every set of every push.

    For each pair, the committer date of the commit that last touched the source is compared with
    the one that last touched the image. An equal date - two commits pushed together share a second -
    is decided by asking which of the two commits came first in the history. A pair that is not
    committed yet is counted and skipped rather than refused, so the check can be run on a working
    tree while a diagram is being added.

    Args:
        root (str): The folder of the documentation set, inside a git checkout.
        paths (Sequence[str]): The relative paths of the set, as `collect_documentation_paths`
            returns them. Note that it leaves the diagram sources out, so pass the unfiltered list
            (`collect_documentation_paths(root, keep_diagram_sources=True)`) - the sources are what
            is being checked.
        deepen (bool, optional): Whether the history may be fetched when it does not reach back far
            enough to date the diagrams. Defaults to `False`, which reports the set as undatable
            instead; a pipeline that checks out shallowly passes `True`. Only the sets that actually
            have a diagram ever cause a fetch.
        source_format (str): The input format used for pairing; HTML is not checked.

    Returns:
        DiagramReport: The findings, how many pairs were checked, and how many were not committed
            yet.
    """
    if not pairs:
        return DiagramReport(pairs_checked=0)

    if not _is_git_checkout(root):
        return DiagramReport(pairs_checked=len(pairs), findings=[DiagramFinding(
            code=DiagramFindingCode.UNDATABLE_DIAGRAM_HISTORY,
            message=(f"The documentation set holds {len(pairs)} diagram source/image pair(s), but "
                     f"'{root}' is not inside a git checkout, so there is no way to tell whether "
                     f"the images were exported after the diagrams were last edited."))])

    tracked = [path for pair in pairs for path in (pair.source, pair.image)]
    if deepen:
        _deepen_until_datable(root, tracked)

    undatable = _boundary_dated(root, tracked)
    if undatable:
        return DiagramReport(pairs_checked=len(pairs), findings=[DiagramFinding(
            code=DiagramFindingCode.UNDATABLE_DIAGRAM_HISTORY,
            message=(f"The history of the checkout does not reach back to the commits that last "
                     f"touched {len(undatable)} of the {len(tracked)} file(s) of this set's "
                     f"diagrams, so their dates cannot be compared. Check out with the history - a "
                     f"shallow clone answers with its boundary commit for every older file, which "
                     f"would let a diagram whose image was never re-exported through unnoticed."))])

    findings: List[DiagramFinding] = []
    uncommitted = 0
    for pair in pairs:
        source = _last_commit(root, pair.source)
        image = _last_commit(root, pair.image)
        if source is None or image is None:
            uncommitted += 1
            continue
        if _is_stale(root, source, image):
            findings.append(DiagramFinding(
                code=DiagramFindingCode.STALE_DIAGRAM_IMAGE,
                path=pair.source,
                message=(f"'{pair.source}' was changed after '{pair.image}' was exported from it "
                         f"(source {source[2]}, image {image[2]}), so the documentation shows an "
                         f"older picture than the diagram it is kept with. Open the source, export "
                         f"it over the image next to it and commit both files.")))

    return DiagramReport(pairs_checked=len(pairs), findings=findings, pairs_uncommitted=uncommitted)


def _name_of(path: str) -> str:
    """The file name of a relative set path."""
    separator = path.rfind("/")
    return path[separator + 1:] if separator >= 0 else path


def _extension_of(path: str) -> str:
    """The lower-cased extension after the last dot of the file name, `''` when there is none."""
    name = _name_of(path)
    separator = name.rfind(".")
    if separator <= 0:
        return ""
    return name[separator + 1:].lower()


def _stem_of(name: str) -> str:
    """The file name without its last extension."""
    separator = name.rfind(".")
    return name[:separator] if separator > 0 else name


def _images_claiming(name: str, images: Sequence[str]) -> List[str]:
    """Every export format of the most specific image stem `name` extends, sorted."""
    claimed_length = -1
    for image in images:
        stem = _stem_of(_name_of(image))
        if stem == name or not name.startswith(f"{stem}."):
            continue
        claimed_length = max(claimed_length, len(stem))
    if claimed_length < 0:
        return []
    return sorted(image for image in images
                  if len(_stem_of(_name_of(image))) == claimed_length
                  and name.startswith(f"{_stem_of(_name_of(image))}."))


def _git(root: str, *arguments: str) -> subprocess.CompletedProcess:
    """Run git in the folder of the documentation set, never raising on a non-zero status."""
    return subprocess.run(["git", "--literal-pathspecs", "-C", root, *arguments],
                          capture_output=True, text=True, check=False, timeout=_GIT_TIMEOUT)


def _is_git_checkout(root: str) -> bool:
    """Whether the folder of the documentation set is inside a git work tree."""
    return _git(root, "rev-parse", "--git-dir").returncode == 0


def _last_commit(root: str, path: str) -> Optional[Tuple[str, int, str]]:
    """The commit that last touched `path`, as `(sha, unix timestamp, ISO date)`, or `None`."""
    completed = _git(root, "log", "-1", "--format=%H %ct %cI", "--", path)
    if completed.returncode != 0:
        raise _HistoryError(f"git log failed for '{path}' (exit {completed.returncode}).")
    if not completed.stdout.strip():
        return None
    sha, timestamp, iso = completed.stdout.strip().split(" ", 2)
    return sha, int(timestamp), iso


def _shallow_boundary(root: str) -> FrozenSet[str]:
    """The commits a shallow history is grafted at. Empty for a complete checkout."""
    state = _git(root, "rev-parse", "--is-shallow-repository")
    if state.returncode != 0 or state.stdout.strip() not in {"true", "false"}:
        raise _HistoryError("Cannot determine whether the Git checkout is shallow.")
    if state.stdout.strip() == "false":
        return frozenset()
    completed = _git(root, "rev-parse", "--git-path", "shallow")
    value = completed.stdout.rstrip("\n")
    if completed.returncode != 0 or not value or "\n" in value or value.startswith("--"):
        raise _HistoryError("Cannot locate the Git shallow boundary file.")
    shallow = os.path.join(root, value)
    if not os.path.isfile(shallow):
        raise _HistoryError("Shallow checkout has no readable shallow boundary file.")
    with open(shallow, "r", encoding="utf-8") as handle:
        boundary = frozenset(line.strip() for line in handle if line.strip())
    if not boundary:
        raise _HistoryError("Shallow boundary file is empty.")
    return boundary


def _boundary_dated(root: str, paths: Sequence[str]) -> List[str]:
    """
    The paths whose date would come from the shallow boundary, and is therefore no date at all.

    `git log -1 -- <path>` answers with the grafted commit for every file last touched beyond it, an
    answer indistinguishable from "really changed there".
    """
    boundary = _shallow_boundary(root)
    if not boundary:
        return []
    undatable = []
    for path in paths:
        commit = _last_commit(root, path)
        if commit is not None and commit[0] in boundary:
            undatable.append(path)
    return undatable


def _deepen_until_datable(root: str, paths: Sequence[str]) -> None:
    """
    Fetch history until the diagrams can be dated, in rounds, then all of it.

    Deepening in rounds rather than unshallowing outright keeps the common case - a diagram touched
    recently - to one small fetch.
    """
    for depth in _DEEPEN_ROUNDS:
        if not _boundary_dated(root, paths):
            return
        if _git(root, "fetch", "--quiet", "--deepen", str(depth)).returncode != 0:
            break
    if _boundary_dated(root, paths):
        _git(root, "fetch", "--quiet", "--unshallow")


def _is_stale(root: str,
              source: Tuple[str, int, str],
              image: Tuple[str, int, str]) -> bool:
    """
    Whether the source was committed after the image was.

    The committer dates decide. They have a resolution of one second though, and two commits pushed
    together can share one, so an equal date is resolved by asking which commit came first in the
    history: if the image's commit is an ancestor of the source's, the export predates the edit and
    the image is stale after all.
    """
    source_sha, source_timestamp, _ = source
    image_sha, image_timestamp, _ = image
    if source_timestamp > image_timestamp:
        return True
    if source_timestamp < image_timestamp or source_sha == image_sha:
        return False
    result = _git(root, "merge-base", "--is-ancestor", image_sha, source_sha)
    if result.returncode not in (0, 1):
        raise _HistoryError("Cannot compare diagram commit ancestry.")
    return result.returncode == 0
