"""The content responsibility of the two-stage validation of a documentation set.

A documentation set is validated in two places. Its **structure** - which folders exist, which
extensions they may carry, which names the generator owns - is the jEAP doc service's, which knows
the structure template. Its **content** is this module's, checked in the pipeline before anything is
sent: the doc service never sees a file's bytes.

Four things are checked, and they are the ones that would otherwise fail a site build twenty minutes
later, far away from the person who wrote the page:

1. the file is text - valid UTF-8 without a NUL byte;
2. it parses as CommonMark, which is how the published site reads it;
3. its front matter is a YAML mapping whose keys are on an allowlist, so a page cannot reach into
   how the site is assembled - `slug` above all, which would change the page's URL;
4. every relative link and image resolves to a file in the same documentation set.

What is deliberately not checked: `http(s)` and `mailto` links (a link checker that reaches the
internet makes a build flaky), anchors (a heading may come from a generated page in the same
chapter), site-absolute links (they resolve against the published site, which a pipeline does not
have), and missing front matter (the site derives a title from the first heading).
"""

import posixpath
from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet, List, Optional, Sequence, Set, Tuple
from urllib.parse import unquote, urlparse

import yaml
from markdown_it import MarkdownIt

#: The front matter keys a page may carry. Everything a page legitimately says about itself, and
#: nothing that changes its identity, its URL or its place in the navigation - those come from the
#: folder the page sits in and from what the doc service generates beside it.
ALLOWED_FRONT_MATTER_KEYS: FrozenSet[str] = frozenset({
    "title", "description", "sidebar_label", "tags", "keywords",
})

#: The most findings one report carries, matching the doc service's own default.
DEFAULT_MAX_FINDINGS = 50

_MARKDOWN_EXTENSION = ".md"
_FRONT_MATTER_FENCE = "---"


class _StrictSafeLoader(yaml.SafeLoader):
    """
    A safe YAML loader that refuses a mapping carrying one key twice.

    `yaml.safe_load` keeps the last of two equal keys without a word, while the parser the site is
    built with rejects them - so a page with `title` twice would pass here and fail there, which is
    the one thing this check exists to prevent.
    """

    def construct_mapping(self, node, deep=False):
        keys = []
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in keys:
                raise yaml.constructor.ConstructorError(
                    None, None, f"the key '{key}' is written twice", key_node.start_mark)
            keys.append(key)
        return super().construct_mapping(node, deep=deep)


class ContentFindingCode(str, Enum):
    """What is wrong with the content of a page."""

    INVALID_ENCODING = "INVALID_ENCODING"
    MALFORMED_MARKDOWN = "MALFORMED_MARKDOWN"
    MALFORMED_FRONT_MATTER = "MALFORMED_FRONT_MATTER"
    FORBIDDEN_FRONT_MATTER_KEY = "FORBIDDEN_FRONT_MATTER_KEY"
    DEAD_LINK = "DEAD_LINK"
    LINK_WITHOUT_EXTENSION = "LINK_WITHOUT_EXTENSION"
    LINK_OUT_OF_SET = "LINK_OUT_OF_SET"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class ContentFinding:
    """One problem with one page, and where in it."""

    code: ContentFindingCode
    path: str
    message: str
    line: Optional[int] = None


@dataclass(frozen=True)
class ContentReport:
    """What the content check found in a documentation set."""

    files_checked: int
    findings: List[ContentFinding] = field(default_factory=list)
    findings_omitted: int = 0

    @property
    def accepted(self) -> bool:
        """Whether the content check found nothing to report."""
        return not self.findings and self.findings_omitted == 0


def validate_documentation_content(root: str,
                                   paths: Sequence[str],
                                   allowed_front_matter_keys: FrozenSet[str] = ALLOWED_FRONT_MATTER_KEYS,
                                   max_findings: int = DEFAULT_MAX_FINDINGS) -> ContentReport:
    """
    Check the Markdown pages of a documentation set, in the pipeline.

    Only `.md` files are read; every other file of the set is a link target and nothing else. The
    findings are ordered by path and line, so two runs over one set report the same list, and capped
    at `max_findings` with the remainder counted rather than dropped in silence.

    Args:
        root (str): The folder of the documentation set.
        paths (Sequence[str]): The relative paths of the set, as
            `collect_documentation_paths` returns them.
        allowed_front_matter_keys (frozenset, optional): The front matter keys a page may carry.
            Defaults to `ALLOWED_FRONT_MATTER_KEYS`.
        max_findings (int, optional): The most findings the report carries. Defaults to
            `DEFAULT_MAX_FINDINGS`.

    Returns:
        ContentReport: The findings, the number of files read, and how many findings were left out.
    """
    known_paths: Set[str] = set(paths)
    markdown_paths = [path for path in paths if path.lower().endswith(_MARKDOWN_EXTENSION)]
    parser = MarkdownIt("commonmark")

    findings: List[ContentFinding] = []
    for path in markdown_paths:
        findings.extend(_check_page(root, path, known_paths, allowed_front_matter_keys, parser))

    findings.sort(key=lambda finding: (finding.path, finding.line or 0, finding.code.value))
    omitted = max(0, len(findings) - max_findings)
    return ContentReport(files_checked=len(markdown_paths),
                         findings=findings[:max_findings],
                         findings_omitted=omitted)


def _check_page(root: str,
                path: str,
                known_paths: Set[str],
                allowed_front_matter_keys: FrozenSet[str],
                parser: MarkdownIt) -> List[ContentFinding]:
    """Check one Markdown page and return everything wrong with it."""
    absolute = posixpath.join(root.replace("\\", "/"), path)
    with open(absolute, "rb") as page:
        raw = page.read()

    if b"\x00" in raw:
        return [ContentFinding(ContentFindingCode.INVALID_ENCODING, path,
                               "The file contains a NUL byte, so it is not a text file. "
                               "Documentation is text.")]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        return [ContentFinding(
            ContentFindingCode.INVALID_ENCODING, path,
            f"The file is not valid UTF-8 (byte {error.start} of {len(raw)}). Save it as UTF-8: it "
            f"is the only encoding the site is built with.")]

    findings: List[ContentFinding] = []
    front_matter_lines, body, body_line_offset = _split_front_matter(text)

    if front_matter_lines is None and body_line_offset == -1:
        findings.append(ContentFinding(
            ContentFindingCode.MALFORMED_FRONT_MATTER, path,
            "The front matter block opened with '---' is never closed. Close it with a line of "
            "'---' before the content of the page.", 1))
        body_line_offset = 0
    elif front_matter_lines is not None:
        findings.extend(_check_front_matter(path, front_matter_lines, allowed_front_matter_keys))

    try:
        tokens = parser.parse(body)
    except Exception as exception:  # a parser that cannot read the file at all
        findings.append(ContentFinding(
            ContentFindingCode.MALFORMED_MARKDOWN, path,
            f"The file cannot be parsed as CommonMark: {type(exception).__name__}: {exception}"))
        return findings

    findings.extend(_check_links(path, tokens, body.split("\n"), known_paths, body_line_offset))
    return findings


def _split_front_matter(text: str) -> Tuple[Optional[List[str]], str, int]:
    """
    Split a page into its front matter lines and its body.

    Returns the front matter lines (`None` when there is no front matter block), the body, and the
    number of lines the body is offset by, so a finding in the body names the line of the file. An
    unterminated block is reported as a body offset of -1.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != _FRONT_MATTER_FENCE:
        return None, text, 0

    for index in range(1, len(lines)):
        if lines[index].strip() == _FRONT_MATTER_FENCE:
            return lines[1:index], "\n".join(lines[index + 1:]), index + 1
    return None, text, -1


def _check_front_matter(path: str,
                        front_matter_lines: List[str],
                        allowed_front_matter_keys: FrozenSet[str]) -> List[ContentFinding]:
    """Check that the front matter is a YAML mapping whose keys are allowed."""
    front_matter_text = "\n".join(front_matter_lines)
    try:
        parsed = yaml.load(front_matter_text, Loader=_StrictSafeLoader)
    except yaml.YAMLError as error:
        return [ContentFinding(
            ContentFindingCode.MALFORMED_FRONT_MATTER, path,
            f"The front matter is not valid YAML: {' '.join(str(error).split())}", 1)]

    if parsed is None:
        return []
    if not isinstance(parsed, dict):
        return [ContentFinding(
            ContentFindingCode.MALFORMED_FRONT_MATTER, path,
            "The front matter is not a mapping of keys to values. It is where a page says its "
            "title and its description, one 'key: value' per line.", 1)]

    allowed = ", ".join(sorted(allowed_front_matter_keys))
    findings = []
    for key in sorted(str(key) for key in parsed.keys()):
        if key in allowed_front_matter_keys:
            continue
        findings.append(ContentFinding(
            ContentFindingCode.FORBIDDEN_FRONT_MATTER_KEY, path,
            _forbidden_key_message(key, allowed),
            _front_matter_key_line(front_matter_lines, key)))
    return findings


def _forbidden_key_message(key: str, allowed: str) -> str:
    """Say what a refused front matter key would have done, and what is allowed instead."""
    reasons = {
        "slug": "It would change the page's URL and could collide with a route the doc service "
                "generates.",
        "id": "It would change the page's identity, which the doc service derives from its path.",
        "sidebar_position": "The order of the pages of a chapter comes from the folder, not from "
                            "the page.",
        "sidebar_class_name": "How the navigation looks is the site's, not a page's.",
        "custom_edit_url": "The link to the source is written by the doc service, which knows "
                           "where the page came from.",
        "pagination_next": "The order of the pages of a chapter comes from the folder.",
        "pagination_prev": "The order of the pages of a chapter comes from the folder.",
        "draft": "A page that is not ready belongs on a branch, not in an upload.",
        "unlisted": "A published page is listed; hiding one from the navigation hides it from the "
                    "search index too.",
    }
    reason = reasons.get(key, "Only what a page says about itself is allowed.")
    return f"'{key}' is not allowed in front matter. {reason} Allowed: {allowed}."


def _front_matter_key_line(front_matter_lines: List[str], key: str) -> int:
    """The line of the file a front matter key is written on, counting the opening fence."""
    for index, line in enumerate(front_matter_lines):
        stripped = line.strip()
        if stripped.startswith(key) and stripped[len(key):].lstrip().startswith(":"):
            return index + 2
    return 1


def _check_links(path: str,
                 tokens,
                 body_lines: List[str],
                 known_paths: Set[str],
                 body_line_offset: int) -> List[ContentFinding]:
    """Check every relative link and image of a page against the paths of the set."""
    findings = []
    for target, line, is_image in _links_of(tokens, body_lines, body_line_offset):
        finding = _check_link(path, target, line, is_image, known_paths)
        if finding:
            findings.append(finding)
    return findings


def _links_of(tokens, body_lines: List[str], body_line_offset: int):
    """Yield the target, the line and the kind of every link and image of a parsed page."""
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        block_start = token.map[0] if token.map else 0
        block_end = token.map[1] if token.map else block_start + 1
        block = "\n".join(body_lines[block_start:block_end])
        cursor = 0
        for child in token.children:
            if child.type == "link_open":
                target, is_image = child.attrGet("href"), False
            elif child.type == "image":
                target, is_image = child.attrGet("src"), True
            else:
                continue
            if not target:
                continue
            line, cursor = _line_in_block(block, target, cursor)
            yield target, block_start + line + body_line_offset + 1, is_image


def _line_in_block(block: str, target: str, cursor: int) -> Tuple[int, int]:
    """
    The line a link target is written on, as an index into the lines of its block.

    The parser gives a line per **block** - one paragraph, one table, one list item - and a block
    spans lines, so the line of the block is not the line of the link. A finding is reported on the
    line a person has to edit, so the target is looked for in the source of its block.

    Args:
        block (str): The source of the block, as the page has it.
        target (str): The target the parser read out of it.
        cursor (int): Where in the block to start looking - after the last target found in it, so a
            page linking one target twice reports the second one where the second one stands.

    Returns:
        Tuple[int, int]: The line, as an index into the lines of the block, and the cursor to look
            for the next target from. A target the parser rewrote - resolved from a reference
            definition somewhere else, above all - is not in the block as written; the line is then
            the one the search started on and the cursor does not move.
    """
    for candidate in (target, unquote(target)):
        found = block.find(candidate, cursor)
        if found >= 0:
            return block.count("\n", 0, found), found + len(candidate)
    return block.count("\n", 0, cursor), cursor


def _check_link(path: str,
                target: str,
                line: int,
                is_image: bool,
                known_paths: Set[str]) -> Optional[ContentFinding]:
    """Check one link target, or return `None` when it is not ours to check."""
    # An anchor stays on the page; a target opening with a slash is site-absolute or
    # protocol-relative, and both resolve against something a pipeline does not have.
    if target.startswith("#") or target.startswith("/"):
        return None
    parsed = urlparse(target)
    if parsed.scheme:
        return None
    if not parsed.path:
        return None

    relative = unquote(parsed.path)
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(path), relative))
    kind = "image" if is_image else "link"

    if resolved.startswith(".."):
        return ContentFinding(
            ContentFindingCode.LINK_OUT_OF_SET, path,
            f"The {kind} '{target}' points outside the documentation folder. Only the files of "
            f"this folder are uploaded, so it resolves to nothing once the page is published.",
            line)

    if resolved in known_paths:
        return None

    if not posixpath.splitext(resolved)[1] and resolved + _MARKDOWN_EXTENSION in known_paths:
        return ContentFinding(
            ContentFindingCode.LINK_WITHOUT_EXTENSION, path,
            f"The link '{target}' is missing the '.md' extension. A relative link is resolved to "
            f"the page it names, so write '{target}.md'.", line)

    return ContentFinding(
        ContentFindingCode.DEAD_LINK, path,
        f"The {kind} '{target}' resolves to no file in this documentation set. A page generated by "
        f"the doc service cannot be linked relatively, and a file outside the folder is not "
        f"uploaded.", line)
