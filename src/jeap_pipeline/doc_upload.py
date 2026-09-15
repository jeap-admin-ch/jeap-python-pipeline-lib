"""Uploading the documentation of a repository to the jEAP doc service.

This is the step after the validation: the documentation a repository declares is packed into one ZIP
per set and sent to the doc service, which takes it over into the documentation it generates and asks
for the site to be published. A pipeline calls `upload_documentation_sets` and prints what comes back.

What is platform-specific stays outside: which URL to call, where the client secret comes from, where
the report is written to, and what a repository's version and provenance are. What is not - the
bundle, the idempotency key, the request and every answer the doc service can give - is here, so a
pipeline on another platform reuses it rather than writing it again.
"""

import os
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

import requests

from .doc_path_tree import collect_documentation_paths, documentation_set_root
from .doc_service_operations import (DEFAULT_ATTEMPTS, DocServiceError, DocServiceRequestError,
                                     DocumentationSet, StructureReport, first_line, problem_of,
                                     read_structure_report, refusal_hint)
from .doc_validation import Finding, SetOutcome, findings_of, format_set_report
from .oauth_token import fetch_client_credentials_token

#: Connect and read timeout of an upload, in seconds. The read timeout is the generous one: the doc
#: service answers a `PUT` only after it has stored the bundle and taken the set over.
DEFAULT_UPLOAD_TIMEOUT: Tuple[int, int] = (5, 120)

#: How often an upload that is already being received is repeated. The doc service answers such a
#: request with `409` and a `Retry-After`, so waiting is what it asks for - but a pipeline may not
#: wait forever for an attempt nobody finishes.
DEFAULT_IN_PROGRESS_ATTEMPTS = 5

#: How long to wait for an upload in progress when the answer names no `Retry-After`, in seconds.
DEFAULT_RETRY_AFTER_SECONDS = 10

#: The longest one wait for an upload in progress lasts, in seconds. A `Retry-After` above it is
#: clamped rather than obeyed, so a gateway answering with a day cannot hold a pipeline for a day.
#: The whole wait is bounded by `DEFAULT_IN_PROGRESS_ATTEMPTS` waits of it, after which the upload is
#: given up on.
MAX_RETRY_AFTER_SECONDS = 120

_UPLOAD_PATH = "/api/uploads/docs"

#: What a status means for an upload where it means something else than for a validation.
_STATUS_HINTS: Dict[int, str] = {
    415: "The body was not sent as a ZIP archive.",
    422: "The documentation set would not be published as it is. The findings say which files "
         "break a rule of the structure template.",
}

#: What a pipeline is told to do about each refusal, keyed by the `code` of the problem document.
#: The doc service's message says what is wrong; these say where to fix it.
_HINTS: Dict[str, str] = {
    "MISSING_PARAMETER": "The documentation configuration does not say everything this kind of "
                         "documentation needs.",
    "UNKNOWN_PARAMETER": "A parameter the doc service does not know was sent - most likely a typo "
                         "in the documentation configuration.",
    "INVALID_PARAMETER_VALUE": "A value of the documentation configuration is not one the doc "
                               "service can use.",
    "UNKNOWN_SITE": "The 'site' of the documentation configuration is not one this doc service "
                    "serves.",
    "LENGTH_REQUIRED": "The upload was sent without announcing its size.",
    "CONTENT_LENGTH_MISMATCH": "The bundle was cut short on its way to the doc service. Running "
                               "the pipeline again sends it whole.",
    "SIZE_LIMIT_EXCEEDED": "The bundle is larger than the doc service accepts.",
    "TOO_MANY_PATHS": "The documentation set holds more files than a set may.",
    "UNPACKS_TO_TOO_MUCH": "The bundle unpacks to more than the doc service accepts.",
    "INVALID_BUNDLE": "The doc service cannot read the bundle as a ZIP archive.",
    "UPLOAD_ID_CONFLICT": "The upload id was already used for an upload describing something else - "
                          "or the same id was repeated with a different provenance, and "
                          "'generated-at' has to be the same on every attempt of one upload.",
    "UPLOAD_IN_PROGRESS": "Another attempt of this upload was still being received after the waits "
                          "this pipeline makes. Running the pipeline again takes the upload over "
                          "once that attempt has timed out.",
}


@dataclass(frozen=True)
class UploadProvenance:
    """
    Where an uploaded documentation set comes from, as the doc service renders it under every page.

    It describes the commit and the run that uploaded the documentation, so none of it is configured
    in a repository: a pipeline resolves it from its checkout and from the run it is part of.

    **Every attempt of one upload sends the same provenance**, `generated_at` and `build_url`
    included: the doc service compares the whole description of a repeated upload id, so a value
    computed afresh per attempt makes the second one a conflict. Resolve it once per run.
    """

    source_repository: str
    source_revision: str
    source_ref: str
    source_timestamp: str
    build_url: Optional[str] = None
    generated_at: Optional[str] = None

    def query_parameters(self) -> Dict[str, str]:
        """The provenance as the query parameters of an upload."""
        parameters = {
            "source-repository": self.source_repository,
            "source-revision": self.source_revision,
            "source-ref": self.source_ref,
            "source-timestamp": self.source_timestamp,
        }
        if self.build_url:
            parameters["build-url"] = self.build_url
        if self.generated_at:
            parameters["generated-at"] = self.generated_at
        return parameters


@dataclass(frozen=True)
class UploadResult:
    """What the doc service answered an upload with."""

    upload_id: str
    status_code: int
    id: Optional[int] = None
    state: Optional[str] = None
    size_in_bytes: int = 0

    @property
    def stored(self) -> bool:
        """Whether this request stored the bundle, rather than repeating an upload already stored."""
        return self.status_code == 201


@dataclass(frozen=True)
class SetUploadOutcome:
    """What became of one documentation set."""

    documentation_set: DocumentationSet
    files: int = 0
    size_in_bytes: int = 0
    result: Optional[UploadResult] = None
    structure: Optional[StructureReport] = None
    report: str = ""

    @property
    def uploaded(self) -> bool:
        """Whether the set reached the doc service."""
        return self.result is not None

    @property
    def refused(self) -> bool:
        """Whether the doc service refused the set over its structure."""
        return self.structure is not None

    @property
    def accepted(self) -> bool:
        """Whether the set is on its way to the site."""
        return self.uploaded


@dataclass(frozen=True)
class DocumentationUploadOutcome:
    """What became of every documentation set of a repository."""

    sets: List[SetUploadOutcome] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    report: str = ""

    @property
    def accepted(self) -> bool:
        """Whether every set reached the doc service."""
        return all(outcome.accepted for outcome in self.sets)

    @property
    def uploaded_sets(self) -> int:
        """How many sets reached the doc service."""
        return sum(1 for outcome in self.sets if outcome.uploaded)


def upload_documentation_sets(documentation_sets: Sequence[DocumentationSet],
                              doc_service_url: str,
                              token_uri: str,
                              client_id: str,
                              client_secret: str,
                              provenance: UploadProvenance,
                              versions: Optional[Dict[str, str]] = None,
                              version_source: Optional[str] = None,
                              upload_id_seed: Optional[str] = None,
                              working_directory: str = ".") -> DocumentationUploadOutcome:
    """
    Upload every documentation set of a repository to the jEAP doc service.

    One token is fetched for all of them. **Every set is resolved and walked before the first one is
    sent** - what it says about itself, and the folder it is in - so a component without a version or
    a `path` that is a typo fails the run while nothing is published yet, rather than after half the
    documentation is already stored.

    Each set is then packed into a ZIP of exactly the files that were walked and sent under an upload
    id of its own; the doc service answers `201` when it stored the bundle and `200` when the same
    upload had been stored before.

    Which sets a pipeline uploads is its own decision: what is handed in is what is sent, in the
    format it is written in.

    Args:
        documentation_sets (Sequence[DocumentationSet]): The sets to upload, as
            `documentation_sets_from_config` returns them.
        doc_service_url (str): The doc service, origin plus context path, no trailing slash.
        token_uri (str): The token endpoint of the authorization server of that doc service.
        client_id (str): The doc pipeline client of the system.
        client_secret (str): The secret of that client.
        provenance (UploadProvenance): The commit and the run the documentation comes from.
        versions (dict, optional): The version to send per documentation set, keyed by the set's
            `path`. A component's and a library's documentation carries the version of what it
            documents; a system's carries none, and an entry for a `system-docs` set is refused.
        version_source (str, optional): Where the version is expected to come from, for the error
            message when a set that needs one has none - the input of a build step, say.
        upload_id_seed (str, optional): What the upload ids are derived from - the identity of this
            run, so that a retry repeats an id and a re-run does not. Without it every set gets a
            random id, which is right for a caller that has no run identity. An attempt that repeats
            an id has to repeat the `provenance` with it, timestamps included.
        working_directory (str, optional): What the `path` of a set is relative to. Defaults to the
            current directory, which in a pipeline is the checkout.

    Raises:
        DocumentationConfigError: If a set does not say what an upload of it needs - before anything
            is uploaded.
        DocumentationPathError: If the folder of a set does not exist - likewise before anything is
            uploaded.
        OAuthTokenError: If no token can be obtained.
        DocServiceRequestError: If the doc service refuses an upload.
        DocServiceError: If the doc service cannot be reached, or answers in a way nothing can be
            made of.

    Returns:
        DocumentationUploadOutcome: The per-set outcomes, their findings and the rendered report.
    """
    prepared = [_prepare(documentation_set, provenance,
                         (versions or {}).get(documentation_set.path), version_source,
                         upload_id_seed, working_directory)
                for documentation_set in documentation_sets]

    access_token = fetch_client_credentials_token(token_uri, client_id, client_secret)

    outcomes = [_upload_one(doc_service_url, access_token, *preparation)
                for preparation in prepared]

    return DocumentationUploadOutcome(
        sets=outcomes,
        findings=[finding for outcome in outcomes for finding in _findings_of(outcome)],
        report=_format_outcome_report(outcomes))


def upload_id_of(documentation_set: DocumentationSet, upload_id_seed: Optional[str] = None) -> str:
    """
    The idempotency key of one set's upload.

    One upload id is one upload: the doc service stores a bundle once per id, so a retry has to
    repeat it while a re-run has to not. Derived from the seed and the set, the id is the same for
    every attempt of one run and different for the next run, which is exactly that rule - and with no
    seed it is random, because a caller that cannot say which run it is has nothing to be idempotent
    against.

    The provenance sent with a repeated id has to be the same one, `generated-at` and `build-url`
    included: the doc service compares the whole description and answers `UPLOAD_ID_CONFLICT` when
    anything of it moved.

    Args:
        documentation_set (DocumentationSet): The set being uploaded.
        upload_id_seed (str, optional): The identity of the run, for instance
            `"<repository>/<run>/<attempt>"`.

    Returns:
        str: The upload id, a UUID.
    """
    if not upload_id_seed:
        return str(uuid.uuid4())
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{upload_id_seed}/{_identity_of(documentation_set)}"))


def _identity_of(documentation_set: DocumentationSet) -> str:
    """
    What makes one upload of a run a different one from the next.

    The folder alone does not: one run can upload one folder as two sets - a Markdown one and the
    microsite a build generated beside it - and two workflows of one run share the run and the
    attempt. Two uploads sharing an id would be taken for a retry of one another.
    """
    return "/".join(value or "" for value in (documentation_set.type,
                                              documentation_set.subject,
                                              documentation_set.source_format,
                                              documentation_set.location,
                                              documentation_set.topic,
                                              documentation_set.path))


def upload_documentation_bundle(doc_service_url: str,
                                access_token: str,
                                documentation_set: DocumentationSet,
                                bundle_path: str,
                                upload_id: str,
                                parameters: Dict[str, str],
                                timeout: Tuple[int, int] = DEFAULT_UPLOAD_TIMEOUT,
                                attempts: int = DEFAULT_ATTEMPTS,
                                in_progress_attempts: int = DEFAULT_IN_PROGRESS_ATTEMPTS,
                                backoff_seconds: int = 2) -> UploadResult:
    """
    Send one bundle to the doc service, and read what it answers.

    The same file is sent on every attempt: the doc service compares the parameters of a repeated
    upload and not the bytes, so re-packing the folder between two attempts would start a second
    upload under an id that names the first.

    The verdict is the status line - `201` stored, `200` stored before - and everything else raises.
    A `422` carries the findings of a set the doc service would not publish, and they travel with the
    error so a pipeline can print them.

    Args:
        doc_service_url (str): The doc service, origin plus context path and no trailing slash.
        access_token (str): A bearer token of a client holding
            `<system-name>_%<system>_@uploads_#write` for the system of the set.
        documentation_set (DocumentationSet): The set being uploaded.
        bundle_path (str): The ZIP archive of the set.
        upload_id (str): The idempotency key of this upload.
        parameters (dict): What the upload says about itself, as
            `DocumentationSet.upload_query_parameters` builds it. Resolved by the caller, so a set
            that cannot say it is refused before anything is sent.
        timeout (tuple, optional): Connect and read timeout in seconds.
        attempts (int, optional): How often to try when the doc service cannot be reached or answers
            with a server error.
        in_progress_attempts (int, optional): How often to repeat an upload another attempt is
            receiving.
        backoff_seconds (int, optional): Seconds to wait between attempts.

    Raises:
        DocServiceRequestError: If the doc service refuses the upload.
        DocServiceError: If the doc service cannot be reached, or answers in a way nothing can be
            made of.

    Returns:
        UploadResult: What the doc service answered.
    """
    url = f"{doc_service_url.rstrip('/')}{_UPLOAD_PATH}/{upload_id}"
    size = os.path.getsize(bundle_path)

    print(f"Uploading {documentation_set.path} to {url}")

    attempts = max(1, attempts)
    in_progress_attempts = max(1, in_progress_attempts)
    in_progress = 0
    attempt = 0
    last_error = None
    while attempt < attempts:
        attempt += 1
        try:
            with open(bundle_path, "rb") as bundle:
                response = requests.put(url, params=parameters, data=bundle,
                                        headers=_headers(access_token, size), timeout=timeout)
        except requests.exceptions.RequestException as exception:
            last_error = f"{type(exception).__name__}: {exception}"
            print(f"Attempt {attempt} of {attempts} could not reach the doc service: {last_error}")
            if attempt < attempts:
                time.sleep(backoff_seconds)
            continue

        if response.status_code in (200, 201):
            return _result_of(response, upload_id, documentation_set)

        if _is_upload_in_progress(response):
            in_progress += 1
            if in_progress >= in_progress_attempts:
                raise _refusal(response, documentation_set, url)
            # Another attempt of this upload is being received. The doc service says when it is
            # worth coming back, and repeating is what it asks for rather than an error.
            waiting = _retry_after_of(response)
            print(f"The doc service is receiving another attempt of the upload {upload_id}; "
                  f"repeating in {waiting}s")
            time.sleep(waiting)
            attempt -= 1
            continue

        if response.status_code < 500:
            raise _refusal(response, documentation_set, url)

        last_error = f"status {response.status_code}: {first_line(response.text)}"
        print(f"Attempt {attempt} of {attempts} was answered with {last_error}")
        if attempt < attempts:
            time.sleep(backoff_seconds)

    raise DocServiceError(
        f"The doc service at {url} did not answer the upload of {documentation_set.path} in "
        f"{attempts} attempt(s). Last: {last_error}")


def write_documentation_bundle(root: str, paths: Sequence[str], bundle_path: str) -> int:
    """
    Write the ZIP archive of one documentation set.

    The archive holds exactly the paths it is given, under the names they have inside the set, so the
    folder inside the archive is the chapter folder the doc service sorts the pages into - and what
    was validated is what is uploaded.

    Args:
        root (str): The folder of the documentation set.
        paths (Sequence[str]): The relative paths of its files, as `collect_documentation_paths`
            returns them.
        bundle_path (str): Where to write the archive.

    Returns:
        int: The size of the archive in bytes.
    """
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in paths:
            bundle.write(os.path.join(root, path), arcname=path)
    return os.path.getsize(bundle_path)


def format_set_upload_report(outcome: SetUploadOutcome) -> str:
    """
    Render what became of one documentation set as the text a workflow prints.

    Args:
        outcome (SetUploadOutcome): What became of the set, uploaded or refused.

    Returns:
        str: The report, plain text, with nothing specific to a pipeline platform in it.
    """
    documentation_set = outcome.documentation_set
    if outcome.structure is not None:
        return _refusal_report(documentation_set, outcome.structure, outcome.files)

    result = outcome.result
    lines = [f"Uploading {documentation_set.describe()}",
             f"  {outcome.files} file(s), {_human_size(outcome.size_in_bytes)}"]
    if result.stored:
        lines.append(f"  201 Created - upload {result.upload_id}"
                     + (f", state {result.state}" if result.state else ""))
    else:
        lines.append(f"  200 OK - upload {result.upload_id} had already been stored"
                     + (f", state {result.state}" if result.state else ""))
    lines.append("  The documentation site publishes it with its next build.")
    return "\n".join(lines) + "\n"


def _prepare(documentation_set: DocumentationSet,
             provenance: UploadProvenance,
             version: Optional[str],
             version_source: Optional[str],
             upload_id_seed: Optional[str],
             working_directory: str) -> Tuple[DocumentationSet, Dict[str, str], str, str, List[str]]:
    """
    Everything about one set that can be known before anything is sent.

    Resolving and walking have no side effect, so doing both for every set first is what makes a run
    publish all of its sets or none of them.
    """
    root = documentation_set_root(documentation_set.path, working_directory)
    return (documentation_set,
            documentation_set.upload_query_parameters(provenance.query_parameters(), version,
                                                      version_source),
            upload_id_of(documentation_set, upload_id_seed),
            root,
            collect_documentation_paths(root))


def _upload_one(doc_service_url: str,
                access_token: str,
                documentation_set: DocumentationSet,
                parameters: Dict[str, str],
                upload_id: str,
                root: str,
                paths: List[str]) -> SetUploadOutcome:
    """Pack and send, for one documentation set that is already resolved and walked."""
    with tempfile.TemporaryDirectory(prefix="jeap-doc-upload-") as directory:
        bundle_path = os.path.join(directory, "documentation.zip")
        size = write_documentation_bundle(root, paths, bundle_path)
        try:
            result = upload_documentation_bundle(doc_service_url, access_token, documentation_set,
                                                 bundle_path, upload_id, parameters)
        except DocServiceRequestError as refused:
            # A set the doc service would not publish is an answer about the documentation, not a
            # failed request: the findings belong in the report, beside the sets that went through.
            if refused.report is None:
                raise
            return _refused(documentation_set, refused.report, len(paths), size)

    return _reported(SetUploadOutcome(documentation_set=documentation_set, files=len(paths),
                                      size_in_bytes=size, result=result))


def _refused(documentation_set: DocumentationSet,
             structure: StructureReport,
             files: int,
             size_in_bytes: int) -> SetUploadOutcome:
    """A set the doc service refused, reported in the layout the validation reports findings in."""
    return SetUploadOutcome(documentation_set=documentation_set, files=files,
                            size_in_bytes=size_in_bytes, structure=structure,
                            report=_refusal_report(documentation_set, structure, files))


def _refusal_report(documentation_set: DocumentationSet, structure: StructureReport,
                    files: int) -> str:
    """The findings of a refused set, in the layout the validation prints them in."""
    return format_set_report(SetOutcome(documentation_set=documentation_set, structure=structure),
                             files, heading=f"Uploading {documentation_set.describe()}")


def _findings_of(outcome: SetUploadOutcome) -> List[Finding]:
    """
    The findings of one set, flattened the way the validation flattens its own.

    A set nothing was found about has none, so a pipeline annotates the files of a refused upload
    with the same loop it uses after a validation.
    """
    if outcome.structure is None:
        return []
    return findings_of(SetOutcome(documentation_set=outcome.documentation_set,
                                  structure=outcome.structure))


def _reported(outcome: SetUploadOutcome) -> SetUploadOutcome:
    """One outcome with its report rendered."""
    return replace(outcome, report=format_set_upload_report(outcome))


def _headers(access_token: str, size: int) -> Dict[str, str]:
    """
    The headers of an upload.

    `Content-Length` is announced explicitly: the doc service rejects a bundle that is too large
    before it is transferred, and recognises a body cut short by it.
    """
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/zip",
        "Content-Length": str(size),
        "Accept": "application/json, application/problem+json",
    }


def _result_of(response, upload_id: str, documentation_set: DocumentationSet) -> UploadResult:
    """Read a `200` or a `201` into a result."""
    answer = _answer_of(response, documentation_set)
    return UploadResult(upload_id=str(answer.get("uploadId") or upload_id),
                        status_code=response.status_code,
                        id=answer.get("id"),
                        state=answer.get("state"),
                        size_in_bytes=_int_or_zero(answer.get("sizeInBytes")))


def _answer_of(response, documentation_set: DocumentationSet) -> Dict:
    """The body of an answer, as the object it has to be."""
    try:
        answer = response.json()
    except ValueError:
        raise DocServiceError(
            f"The doc service answered the upload of {documentation_set.path} with status "
            f"{response.status_code} and something that is not JSON: "
            f"{first_line(response.text)}") from None
    if not isinstance(answer, dict):
        raise DocServiceError(
            f"The doc service answered the upload of {documentation_set.path} with status "
            f"{response.status_code} and JSON that is not an object: {first_line(response.text)}")
    return answer


def _is_upload_in_progress(response) -> bool:
    """Whether the answer says another attempt of this upload is being received."""
    return response.status_code == 409 and problem_of(response)[0] == "UPLOAD_IN_PROGRESS"


def _retry_after_of(response) -> int:
    """
    How long the doc service asks the caller to wait, in seconds, clamped to what is worth waiting.

    A `Retry-After` above the clamp is waited out at the clamp and the attempt is repeated; what ends
    the waiting is `in_progress_attempts`, not this.
    """
    header = (response.headers or {}).get("Retry-After") if hasattr(response, "headers") else None
    try:
        return min(max(1, int(header)), MAX_RETRY_AFTER_SECONDS)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_SECONDS


def _refusal(response, documentation_set: DocumentationSet, url: str) -> DocServiceRequestError:
    """The error a refused upload raises, with the findings when the set is what was refused."""
    report = None
    if response.status_code == 422:
        # The set would not be published as it is. The findings are the same ones the structure
        # validation reports, so a pipeline prints them without knowing which endpoint refused it.
        report = read_structure_report(response, documentation_set, accepted=False, what="upload")
    return DocServiceRequestError(_refusal_message(response, documentation_set, url), report)


def _refusal_message(response, documentation_set: DocumentationSet, url: str) -> str:
    """Say what the doc service refused, and where that is fixed."""
    code, detail = problem_of(response)
    hint = _HINTS.get(code or "") or _STATUS_HINTS.get(response.status_code) \
        or refusal_hint(response.status_code, documentation_set)
    parts = [f"The doc service at {url} refused the upload of {documentation_set.path} with status "
             f"{response.status_code}{f' ({code})' if code else ''}.", hint, detail]
    return " ".join(part.strip() for part in parts if part and part.strip())


def _format_outcome_report(outcomes: Sequence[SetUploadOutcome]) -> str:
    """Render every set's report, and the line that says how it ended."""
    report = "\n".join(outcome.report for outcome in outcomes)
    uploaded = sum(1 for outcome in outcomes if outcome.uploaded)
    refused = sum(1 for outcome in outcomes if outcome.refused)
    if refused:
        report += (f"\nDocumentation upload failed: {refused} of {len(outcomes)} documentation "
                   f"set(s) would not be published as they are.\n")
        return report
    report += f"\nUploaded {uploaded} documentation set(s).\n"
    return report


def _int_or_zero(value) -> int:
    """A count of an answer, or zero when it is not one."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _human_size(size_in_bytes: int) -> str:
    """A size a person reads, in the unit that fits it."""
    if size_in_bytes < 1024:
        return f"{size_in_bytes} B"
    if size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes / 1024:.1f} KB"
    return f"{size_in_bytes / (1024 * 1024):.1f} MB"


