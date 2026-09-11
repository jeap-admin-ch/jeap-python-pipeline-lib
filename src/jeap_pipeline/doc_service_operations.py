"""The documentation sets of a repository, and the jEAP doc service calls that take them.

A repository declares **what it documents** once - the system, and the component or library - and
its **documentation sets** under `docs`: one folder each, with what kind of documentation is in it.
The keys are the query parameters of the doc service's upload endpoint, so a pipeline passes its
configuration through instead of translating it.

The rules of that configuration live here rather than in the pipeline that reads the file: they are
the upload contract - which key is required for which `type`, what a slug is - and every pipeline
that uploads documentation has to apply exactly these.
"""

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

import requests

#: Connect and read timeout of a doc service call, in seconds.
DEFAULT_TIMEOUT: Tuple[int, int] = (5, 60)

#: How often a call is attempted when the doc service answers with a server error or cannot be
#: reached at all. A service being restarted must not fail a documentation build.
DEFAULT_ATTEMPTS = 3

#: The kinds of documentation an upload can carry.
DOCUMENTATION_TYPES: FrozenSet[str] = frozenset({"system-docs", "component-docs", "library-docs"})

#: The formats a documentation set can be written in.
SOURCE_FORMATS: FrozenSet[str] = frozenset({"markdown", "html"})

#: The key holding the documentation sets of a repository.
DOCUMENTATION_SETS_KEY = "docs"

#: The keys the root of a documentation configuration may carry beside `docs`: what the repository
#: documents, which is the same for every set in it. `version` and `site` are part of the upload
#: contract and are kept although a structure validation does not send them; the provenance of an
#: upload - the repository, the revision, the ref, the timestamp, the build - is resolved from the
#: checkout and the pipeline run rather than configured.
SUBJECT_KEYS: FrozenSet[str] = frozenset({"system", "component", "library", "version", "site"})

#: The key a repository states the branches it publishes from under - not part of an upload, so it
#: is read out of the configuration separately rather than joining a documentation set.
PUBLISH_BRANCHES_KEY = "publish-branches"

#: The keys the root may carry.
CONFIGURATION_ROOT_KEYS: FrozenSet[str] = frozenset(
    SUBJECT_KEYS | {DOCUMENTATION_SETS_KEY, PUBLISH_BRANCHES_KEY})

#: The keys one documentation set may carry: what that folder is, which differs from set to set.
DOCUMENTATION_SET_KEYS: FrozenSet[str] = frozenset({
    "path", "type", "template", "source-format", "location", "topic", "label",
})

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_VALIDATION_PATH = "/api/uploads/docs/validation"

# Every value of a documentation configuration is a string. A number or a list would otherwise
# reach the doc service stringified - `system=42` - and come back as a refusal about a system
# nobody named, rather than as the configuration error it is.
_STRING_KEYS = ("path", "type", "system", "template", "source_format", "component", "library",
                "location", "topic", "label", "version", "site")


class DocumentationConfigError(ValueError):
    """Raised when the documentation configuration of a repository cannot be read."""


class DocServiceError(RuntimeError):
    """Raised when the doc service cannot be reached or answers in a way nothing can be made of."""


class DocServiceRequestError(DocServiceError):
    """
    Raised when the doc service refuses the request itself - a wrong parameter, or no permission.

    `report` carries the findings of the one refusal that is about the documentation rather than
    about the request: a set that would not be published as it is. It is `None` for every other
    refusal, so a caller can branch on it without asking which endpoint answered.
    """

    def __init__(self, message: str, report: Optional["StructureReport"] = None):
        super().__init__(message)
        self.report = report


class StructureFindingCode(str, Enum):
    """
    The finding codes of the doc service's structure validation that are known here.

    They are the doc service's API, and a pipeline that prints a message per code branches on them.
    A `StructureFinding` carries its code as a plain string, so a code a newer doc service invented
    is reported unchanged rather than dropped: this enum is what is known, not what is accepted.
    """

    INVALID_PATH = "INVALID_PATH"
    DUPLICATE_PATH = "DUPLICATE_PATH"
    FILE_OUTSIDE_CHAPTER = "FILE_OUTSIDE_CHAPTER"
    UNKNOWN_CHAPTER = "UNKNOWN_CHAPTER"
    NESTED_FOLDER = "NESTED_FOLDER"
    HIDDEN_NAME = "HIDDEN_NAME"
    UNPUBLISHABLE_NAME = "UNPUBLISHABLE_NAME"
    FORBIDDEN_EXTENSION = "FORBIDDEN_EXTENSION"
    RESERVED_NAME = "RESERVED_NAME"
    COLLIDING_NAME = "COLLIDING_NAME"
    UNKNOWN_TEMPLATE = "UNKNOWN_TEMPLATE"
    EMPTY_TREE = "EMPTY_TREE"
    MISSING_ENTRY_POINT = "MISSING_ENTRY_POINT"
    UNKNOWN_LOCATION = "UNKNOWN_LOCATION"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class DocumentationSet:
    """
    One folder of documentation, and what it is.

    The field names are the keys of the documentation configuration with their hyphens turned into
    underscores; `from_config_entry` maps one onto the other.
    """

    # Every field has a default so that a configuration entry missing a required key is reported
    # as the configuration error it is, rather than as a TypeError from the constructor.
    path: Optional[str] = None
    type: Optional[str] = None
    system: Optional[str] = None
    template: Optional[str] = None
    source_format: Optional[str] = None
    component: Optional[str] = None
    library: Optional[str] = None
    location: Optional[str] = None
    topic: Optional[str] = None
    label: Optional[str] = None
    version: Optional[str] = None
    site: Optional[str] = None

    def __post_init__(self):
        _check_documentation_set(self)

    @property
    def subject(self) -> str:
        """What the documentation is about - the component, the library, or the system itself."""
        return self.component or self.library or self.system

    def describe(self) -> str:
        """One line naming the set, for a report a person reads."""
        return (f"{self.path} ({self.type}, {self.subject}, {self.template}, "
                f"{self.source_format})")

    @classmethod
    def from_config_entry(cls,
                          entry: Dict[str, Any],
                          subject: Optional[Dict[str, Any]] = None) -> "DocumentationSet":
        """
        Build a documentation set from one entry of `docs` and what the repository documents.

        Args:
            entry (dict): The entry as it is written in the configuration file, with the keys of the
                upload contract - `source-format` rather than `source_format`.
            subject (dict, optional): The keys at the root of the configuration - `system` and the
                `component` or `library` - which hold for every set of the repository.

        Raises:
            DocumentationConfigError: If a key is unknown or belongs at the root, a required one is
                missing, one is set that does not belong to the kind of documentation, or a value is
                not a slug.

        Returns:
            DocumentationSet: The typed set.
        """
        if not isinstance(entry, dict):
            raise DocumentationConfigError(
                f"A documentation set has to be an object, not a {type(entry).__name__}.")

        at_the_root = sorted(set(entry.keys()) & (SUBJECT_KEYS | {PUBLISH_BRANCHES_KEY}))
        if at_the_root:
            raise DocumentationConfigError(
                f"{', '.join(repr(key) for key in at_the_root)} belongs at the root of the "
                f"configuration, not to a documentation set: it is the same for every set of a "
                f"repository, so it is said once.")

        unknown = sorted(set(entry.keys()) - DOCUMENTATION_SET_KEYS)
        if unknown:
            raise DocumentationConfigError(
                f"Unknown key(s) {', '.join(repr(key) for key in unknown)}. "
                f"Allowed: {', '.join(sorted(DOCUMENTATION_SET_KEYS))}.")

        values = dict(subject or {})
        values.update(entry)
        return cls(**{key.replace("-", "_"): value for key, value in values.items()})

    def validation_query_parameters(self) -> Dict[str, str]:
        """
        The query parameters of a structure validation - the ones the structure depends on.

        The doc service **refuses** every other parameter of the upload contract with
        `UNKNOWN_PARAMETER`: a path tree does not depend on a commit hash, a version or a site, and
        an endpoint that demanded one to answer a structural question would be answering a
        different one.

        Returns:
            Dict[str, str]: The query parameters, keyed as the endpoint names them.
        """
        parameters = {
            "type": self.type,
            "system": self.system,
            "template": self.template,
            "source-format": self.source_format,
        }
        if self.component:
            parameters["component"] = self.component
        if self.library:
            parameters["library"] = self.library
        if self.source_format == "html":
            parameters["location"] = self.location
            parameters["topic"] = self.topic
        return parameters

    def upload_query_parameters(self,
                                provenance: Dict[str, str],
                                version: Optional[str] = None) -> Dict[str, str]:
        """
        The query parameters of an upload - what the set is, plus where it comes from.

        An upload says everything a validation says and four things more: which commit of which
        repository the documents were taken from, which version of the component or library they
        document, and which site they belong to. The label of an HTML microsite belongs here too,
        because a menu label is not part of a path tree.

        Args:
            provenance (dict): The commit and the run the documentation comes from, keyed as the
                endpoint names them - `source-repository`, `source-revision`, `source-ref`,
                `source-timestamp`, and optionally `build-url` and `generated-at`.
            version (str, optional): The version of the component or library the set documents.
                Without it the `version` of the documentation configuration is sent, which is where
                a repository states one explicitly.

        Raises:
            DocumentationConfigError: If a component's or library's documentation is uploaded
                without a version, or a system's with one. The doc service would answer `400`, and
                a pipeline should say which of its own inputs is missing instead.

        Returns:
            Dict[str, str]: The query parameters, keyed as the endpoint names them.
        """
        parameters = self.validation_query_parameters()
        if self.site:
            parameters["site"] = self.site
        if self.source_format == "html":
            parameters["label"] = self.label

        version = version or self.version
        if self.type in ("component-docs", "library-docs"):
            if not version:
                raise DocumentationConfigError(
                    f"The documentation of the {self.type.split('-')[0]} "
                    f"'{self.subject}' is uploaded with the version of what it documents, and "
                    f"none was resolved. State 'version' at the root of the documentation "
                    f"configuration, or let the pipeline read it from the repository.")
            parameters["version"] = version
        elif version:
            raise DocumentationConfigError(
                f"A version was given for the documentation of the system '{self.system}'. A "
                f"system documents itself; there is no version of a system to name.")

        parameters.update(provenance)
        return parameters


@dataclass(frozen=True)
class StructureFinding:
    """One problem the doc service found with the path tree, and which path it is about."""

    code: str
    message: str
    path: Optional[str] = None


@dataclass(frozen=True)
class StructureReport:
    """The doc service's answer to *would this path tree be accepted?*"""

    accepted: bool
    template: Optional[str] = None
    paths_checked: int = 0
    paths_ignored: int = 0
    allowed_folders: List[str] = field(default_factory=list)
    allowed_extensions: List[str] = field(default_factory=list)
    findings: List[StructureFinding] = field(default_factory=list)
    findings_omitted: int = 0
    detail: Optional[str] = None


def documentation_sets_from_config(configuration: Any,
                                   source: str = "the documentation configuration") -> List[DocumentationSet]:
    """
    Read a documentation configuration into typed documentation sets.

    The configuration is an object: what the repository documents at its root - `system` and the
    `component` or `library` - and its documentation sets under `docs`, one per folder. What a
    repository is is said once and holds for every set in it.

    ```json
    {
      "system": "orders",
      "component": "foo-bar-scs",
      "docs": [
        {"path": "./docs", "type": "component-docs", "template": "arc42",
         "source-format": "markdown"}
      ]
    }
    ```

    Args:
        configuration (Any): The parsed configuration - the object described above.
        source (str, optional): Where the configuration came from, for the error messages. Defaults
            to a generic description.

    Raises:
        DocumentationConfigError: If the configuration is not such an object, if `docs` is not a
            non-empty list, or if a set is wrong. The message names the source and, for a set, its
            index under `docs`.

    Returns:
        List[DocumentationSet]: One set per entry of `docs`, in the order they are configured.
    """
    if not isinstance(configuration, dict):
        raise DocumentationConfigError(
            f"{source} has to hold an object, not a {type(configuration).__name__}: what the "
            f"repository documents at its root, and its documentation sets under "
            f"'{DOCUMENTATION_SETS_KEY}'.")

    unknown = sorted(set(configuration.keys()) - CONFIGURATION_ROOT_KEYS)
    if unknown:
        raise DocumentationConfigError(
            f"{source}: unknown key(s) {', '.join(repr(key) for key in unknown)} at the root of "
            f"the configuration. Allowed: {', '.join(sorted(CONFIGURATION_ROOT_KEYS))}. What a "
            f"single folder is - {', '.join(sorted(DOCUMENTATION_SET_KEYS))} - belongs to an entry "
            f"of '{DOCUMENTATION_SETS_KEY}'.")

    entries = configuration.get(DOCUMENTATION_SETS_KEY)
    if entries is None:
        raise DocumentationConfigError(
            f"{source} names no '{DOCUMENTATION_SETS_KEY}'. It is the list of the documentation "
            f"sets of this repository, one per folder.")
    if not isinstance(entries, list):
        raise DocumentationConfigError(
            f"{source}: '{DOCUMENTATION_SETS_KEY}' has to hold a list of documentation sets, not a "
            f"{type(entries).__name__}. A repository can document more than one folder, so it is a "
            f"list even when it carries one entry.")
    if not entries:
        raise DocumentationConfigError(
            f"{source}: '{DOCUMENTATION_SETS_KEY}' is empty. Remove the file or add a set - a "
            f"pipeline that is asked to validate documentation and finds none configured cannot "
            f"say whether that is right.")

    if configuration.get("component") and configuration.get("library"):
        raise DocumentationConfigError(
            f"{source} names both a 'component' and a 'library' at its root. A repository documents "
            f"one of the two - every documentation set of it inherits what the root says, and a "
            f"component's documentation may not name a library or the other way round.")

    subject = {key: value for key, value in configuration.items() if key in SUBJECT_KEYS}

    sets = []
    for index, entry in enumerate(entries):
        try:
            sets.append(DocumentationSet.from_config_entry(entry, subject))
        except DocumentationConfigError as error:
            raise DocumentationConfigError(
                f"{source}, {DOCUMENTATION_SETS_KEY}[{index}]: {error}") from None
    return sets


def validate_documentation_structure(doc_service_url: str,
                                     access_token: str,
                                     documentation_set: DocumentationSet,
                                     paths: Sequence[str],
                                     timeout: Tuple[int, int] = DEFAULT_TIMEOUT,
                                     attempts: int = DEFAULT_ATTEMPTS,
                                     backoff_seconds: int = 2) -> StructureReport:
    """
    Ask the doc service whether a path tree would be accepted, before anything is uploaded.

    Nothing is uploaded, stored or read by this: the tree travels as a list of paths, and the
    endpoint has no side effect at all.

    The verdict is the status line - `200` accepted, `422` a finding per problem - and both are an
    answer rather than an error. Everything else raises: a `400` means the configuration is wrong, a
    `401` or `403` that the client may not upload for this system, a `413` that `path` points at
    more than the documentation, and a server error is retried first.

    Args:
        doc_service_url (str): The doc service, origin plus context path and no trailing slash, for
            instance `https://docs.example.ch`.
        access_token (str): A bearer token of a client holding
            `<system-name>_%<system>_@uploads_#write` for the system of the set.
        documentation_set (DocumentationSet): The set whose tree is being validated.
        paths (Sequence[str]): The relative paths that would be uploaded.
        timeout (tuple, optional): Connect and read timeout in seconds.
        attempts (int, optional): How often to try when the service cannot be reached or answers
            with a server error. Defaults to `DEFAULT_ATTEMPTS`.
        backoff_seconds (int, optional): Seconds to wait between attempts.

    Raises:
        DocServiceRequestError: If the doc service refuses the request itself.
        DocServiceError: If the doc service cannot be reached, or answers in a way nothing can be
            made of.

    Returns:
        StructureReport: The report, `accepted` saying which of the two answers it was.
    """
    url = doc_service_url.rstrip("/") + _VALIDATION_PATH
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, application/problem+json",
    }
    body = json.dumps({"paths": list(paths)})
    parameters = documentation_set.validation_query_parameters()

    print(f"Validating the structure of {documentation_set.path} against {url}")

    attempts = max(1, attempts)
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(url, params=parameters, data=body.encode("utf-8"),
                                     headers=headers, timeout=timeout)
        except requests.exceptions.RequestException as exception:
            last_error = f"{type(exception).__name__}: {exception}"
            print(f"Attempt {attempt} of {attempts} could not reach the doc service: {last_error}")
            if attempt < attempts:
                time.sleep(backoff_seconds)
            continue

        if response.status_code in (200, 422):
            return read_structure_report(response, documentation_set)
        if response.status_code < 500:
            raise DocServiceRequestError(_request_error_message(response, documentation_set, url))

        last_error = f"status {response.status_code}: {first_line(response.text)}"
        print(f"Attempt {attempt} of {attempts} was answered with {last_error}")
        if attempt < attempts:
            time.sleep(backoff_seconds)

    raise DocServiceError(
        f"The doc service at {url} did not answer the structure validation of "
        f"{documentation_set.path} in {attempts} attempt(s). Last: {last_error}")


def read_structure_report(response,
                          documentation_set: DocumentationSet,
                          accepted: Optional[bool] = None,
                          what: str = "structure validation") -> StructureReport:
    """
    Read the report the doc service answers a path tree with.

    Shared with the upload, which is refused with the same report in the same members when a set
    would not be published as it is - so a pipeline prints the findings without having to know which
    of the two endpoints answered.

    Args:
        response: The answer of the doc service.
        documentation_set (DocumentationSet): The set the answer is about, for the error messages.
        accepted (bool, optional): Whether the answer is the accepting one. By default the status
            line decides, which is what it does on the validation endpoint.
        what (str, optional): What was being done, for the error messages - an unreadable answer to
            an upload must not be reported as a failed validation that never ran.

    Raises:
        DocServiceError: If the answer is not the report it has to be.

    Returns:
        StructureReport: The report.
    """
    try:
        answer = response.json()
    except ValueError:
        raise DocServiceError(
            f"The doc service answered the {what} of {documentation_set.path} with status "
            f"{response.status_code} and something that is not JSON: "
            f"{first_line(response.text)}") from None

    if not isinstance(answer, dict):
        raise DocServiceError(
            f"The doc service answered the {what} of {documentation_set.path} with status "
            f"{response.status_code} and JSON that is not an object: {first_line(response.text)}")

    return StructureReport(
        accepted=response.status_code == 200 if accepted is None else accepted,
        template=answer.get("template"),
        paths_checked=_count_in(answer, "pathsChecked", documentation_set, what),
        paths_ignored=_count_in(answer, "pathsIgnored", documentation_set, what),
        allowed_folders=_strings_in(answer, "allowedFolders"),
        allowed_extensions=_strings_in(answer, "allowedExtensions"),
        findings=_findings_in(answer, documentation_set, what),
        findings_omitted=_count_in(answer, "findingsOmitted", documentation_set, what),
        detail=answer.get("detail"))


def _findings_in(answer: Dict[str, Any],
                 documentation_set: DocumentationSet,
                 what: str) -> List[StructureFinding]:
    """The findings of an answer. A finding this library cannot read is not one it may drop."""
    findings = answer.get("findings") or []
    if not isinstance(findings, list) or any(not isinstance(finding, dict) for finding in findings):
        raise DocServiceError(
            f"The doc service answered the {what} of {documentation_set.path} with a 'findings' "
            f"that is not a list of objects: {first_line(str(findings))}")
    return [StructureFinding(code=str(finding.get("code", "")),
                             message=str(finding.get("message", "")),
                             path=finding.get("path"))
            for finding in findings]


def _count_in(answer: Dict[str, Any], key: str, documentation_set: DocumentationSet,
              what: str) -> int:
    """A count of an answer, which has to be one: a report saying the wrong number says nothing."""
    value = answer.get(key)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        raise DocServiceError(
            f"The doc service answered the {what} of {documentation_set.path} with a '{key}' that "
            f"is not a number: {value!r}") from None


def _strings_in(answer: Dict[str, Any], key: str) -> List[str]:
    """
    A list of strings of an answer, or nothing when the answer carries it in another shape.

    What the template allows is printed beside the findings and is not the verdict, so an answer
    this library cannot read it out of is printed without it rather than refused.
    """
    value = answer.get(key)
    if not isinstance(value, list):
        return []
    return [str(entry) for entry in value]


def _request_error_message(response, documentation_set: DocumentationSet, url: str) -> str:
    """Say what the doc service refused, and what that means for the configuration."""
    code, detail = problem_of(response)
    hint = refusal_hint(response.status_code, documentation_set)
    return (f"The doc service at {url} refused the structure validation of "
            f"{documentation_set.path} with status {response.status_code}"
            f"{f' ({code})' if code else ''}. {hint} {detail}".strip())


def refusal_hint(status_code: int, documentation_set: DocumentationSet) -> str:
    """
    What a refused request means for the configuration, by status.

    Both endpoints below `/api/uploads/docs` answer a wrong request the same way, so what a status
    means to the team that sent it is said once.

    Args:
        status_code (int): The status the doc service answered with.
        documentation_set (DocumentationSet): The set the request was about.

    Returns:
        str: The hint, or an empty string for a status that carries none.
    """
    return {
        400: "The documentation configuration carries a parameter this endpoint does not accept, "
             "or a value that is not one it knows.",
        401: "The request carried no usable token.",
        403: f"The client may not upload documentation for the system "
             f"'{documentation_set.system}'. It needs the role "
             f"<system-name>_%{documentation_set.system}_@uploads_#write.",
        411: "The request was sent without a content length.",
        413: f"The documentation set holds more files than a set may - the doc service names the "
             f"limit in its answer. Either '{documentation_set.path}' points at more than the "
             f"documentation, or the set has to be split.",
        415: "The body was not sent in the media type the endpoint takes.",
    }.get(status_code, "")


def problem_of(response) -> Tuple[Optional[str], str]:
    """
    The `code` and the `detail` of an RFC 9457 problem document, if the answer is one.

    Args:
        response: The answer of the doc service.

    Returns:
        Tuple[Optional[str], str]: The machine-readable code, and the detail or the body.
    """
    try:
        problem = response.json()
    except ValueError:
        return None, first_line(response.text)
    if not isinstance(problem, dict):
        return None, first_line(response.text)
    return problem.get("code"), str(problem.get("detail") or first_line(response.text))


def first_line(text: str, limit: int = 500) -> str:
    """Return the answer of a server in one line, short enough to belong in an error message."""
    if not text:
        return "<empty body>"
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit] + "…"


def _check_documentation_set(documentation_set: DocumentationSet) -> None:
    """Apply the rules of the upload contract to one documentation set."""
    for name in ("path", "type", "system", "template", "source_format"):
        if not getattr(documentation_set, name):
            raise DocumentationConfigError(
                f"'{name.replace('_', '-')}' is required and is missing.")

    for name in _STRING_KEYS:
        value = getattr(documentation_set, name)
        if value is not None and not isinstance(value, str):
            raise DocumentationConfigError(
                f"'{name.replace('_', '-')}' is a {type(value).__name__}, not a string. Every "
                f"value of a documentation configuration is written as a JSON string, quotes "
                f"included.")

    if documentation_set.type not in DOCUMENTATION_TYPES:
        raise DocumentationConfigError(
            f"'type' is '{documentation_set.type}', which is not one of "
            f"{', '.join(sorted(DOCUMENTATION_TYPES))}.")
    if documentation_set.source_format not in SOURCE_FORMATS:
        raise DocumentationConfigError(
            f"'source-format' is '{documentation_set.source_format}', which is not one of "
            f"{', '.join(sorted(SOURCE_FORMATS))}.")

    _check_subject(documentation_set)
    _check_html_placement(documentation_set)
    _check_path(documentation_set.path)

    for name in ("system", "component", "library", "template", "location", "topic", "site"):
        value = getattr(documentation_set, name)
        if value is not None and not _SLUG_PATTERN.match(value):
            raise DocumentationConfigError(
                f"'{name}' is '{value}', which is not a slug: lower case letters, digits and "
                f"single hyphens.")


def _check_subject(documentation_set: DocumentationSet) -> None:
    """`component` belongs to component documentation, `library` to library documentation."""
    expectations = {
        "component-docs": ("component", "library"),
        "library-docs": ("library", "component"),
        "system-docs": (None, None),
    }
    required, forbidden = expectations[documentation_set.type]
    if required and not getattr(documentation_set, required):
        raise DocumentationConfigError(
            f"'{required}' is required for type '{documentation_set.type}' and is missing.")
    if forbidden and getattr(documentation_set, forbidden):
        raise DocumentationConfigError(
            f"'{forbidden}' does not belong to type '{documentation_set.type}'.")
    if documentation_set.type == "system-docs":
        for name in ("component", "library"):
            if getattr(documentation_set, name):
                raise DocumentationConfigError(
                    f"'{name}' does not belong to type 'system-docs', which documents the system "
                    f"itself.")


def _check_html_placement(documentation_set: DocumentationSet) -> None:
    """An HTML microsite says where it is embedded; Markdown is placed by its folders."""
    placement = ("location", "topic", "label")
    if documentation_set.source_format == "html":
        for name in placement:
            if not getattr(documentation_set, name):
                raise DocumentationConfigError(
                    f"'{name}' is required for source-format 'html' and is missing: an HTML "
                    f"microsite cannot be sorted into a chapter by its folder names, so the upload "
                    f"says where it goes.")
    else:
        for name in placement:
            if getattr(documentation_set, name):
                raise DocumentationConfigError(
                    f"'{name}' belongs to source-format 'html' only. Where a Markdown page is "
                    f"published is decided by the chapter folder it sits in.")


def _check_path(path: str) -> None:
    """The folder of a set is relative and stays inside the working directory."""
    normalized = str(path).replace("\\", "/")
    if normalized.startswith("/"):
        raise DocumentationConfigError(
            f"'path' is '{path}', which is absolute. It is relative to the root of the repository.")
    segments = [segment for segment in normalized.split("/") if segment not in ("", ".")]
    depth = 0
    for segment in segments:
        depth += -1 if segment == ".." else 1
        if depth < 0:
            raise DocumentationConfigError(
                f"'path' is '{path}', which leaves the repository. It is relative to the root of "
                f"the repository.")
