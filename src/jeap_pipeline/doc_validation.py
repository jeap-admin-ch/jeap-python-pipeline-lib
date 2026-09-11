"""Validating the documentation of a repository, both responsibilities, in one call.

This is what a pipeline calls. It takes the documentation sets a repository configured, and per set:
walks the folder into a path tree, checks the content of its Markdown pages, asks the jEAP doc
service whether the tree would be accepted, and renders a report a person can act on.

What is left to the platform-specific part is which URL to call, where the client secret comes from,
and where the report is written to.
"""

import textwrap
from dataclasses import dataclass, field, replace
from typing import List, Optional, Sequence

from .doc_content_validation import ContentReport, validate_documentation_content
from .doc_path_tree import collect_documentation_paths, documentation_set_root
from .doc_service_operations import (DocumentationSet, StructureReport,
                                     validate_documentation_structure)
from .oauth_token import fetch_client_credentials_token

_CODE_WIDTH = 28
_LINE_WIDTH = 110
_MIN_MESSAGE_WIDTH = 40


@dataclass(frozen=True)
class Finding:
    """
    One problem, flattened out of the two reports of one documentation set.

    `location` names the responsibility that found it - `content`, checked in the pipeline, or
    `structure`, checked by the doc service. It does not say where in the documentation the problem
    is: that is `path`, and `repository_path` for the file as the repository sees it.
    """

    documentation_set: str
    location: str
    code: str
    message: str
    path: Optional[str] = None
    line: Optional[int] = None

    @property
    def repository_path(self) -> Optional[str]:
        """The path of the file as the repository sees it - the set's folder plus the finding's."""
        if not self.path:
            return None
        folder = self.documentation_set.rstrip("/")
        if folder in (".", ""):
            return self.path
        if folder.startswith("./"):
            folder = folder[2:]
        return f"{folder}/{self.path}"


@dataclass(frozen=True)
class SetOutcome:
    """What both responsibilities said about one documentation set."""

    documentation_set: DocumentationSet
    structure: StructureReport
    content: Optional[ContentReport] = None
    report: str = ""

    @property
    def accepted(self) -> bool:
        """Whether both responsibilities found nothing to report."""
        return self.structure.accepted and (self.content is None or self.content.accepted)


@dataclass(frozen=True)
class DocumentationValidationOutcome:
    """What the validation said about every documentation set of a repository."""

    sets: List[SetOutcome] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    report: str = ""

    @property
    def accepted(self) -> bool:
        """Whether every set was accepted."""
        return all(outcome.accepted for outcome in self.sets)

    @property
    def rejected_sets(self) -> int:
        """How many sets were not accepted."""
        return sum(1 for outcome in self.sets if not outcome.accepted)


def validate_documentation_sets(documentation_sets: Sequence[DocumentationSet],
                                doc_service_url: str,
                                token_uri: str,
                                client_id: str,
                                client_secret: str,
                                working_directory: str = ".") -> DocumentationValidationOutcome:
    """
    Validate every documentation set of a repository, content and structure.

    One token is fetched for all of them. Both checks always run: a structural problem does not hide
    the content problems, and the other way round, because a validation that reported one thing at a
    time would cost a push per mistake.

    Args:
        documentation_sets (Sequence[DocumentationSet]): The sets to validate, as
            `documentation_sets_from_config` returns them.
        doc_service_url (str): The doc service, origin plus context path, no trailing slash.
        token_uri (str): The token endpoint of the authorization server of that doc service.
        client_id (str): The doc pipeline client of the system.
        client_secret (str): The secret of that client.
        working_directory (str, optional): What the `path` of a set is relative to. Defaults to the
            current directory, which in a pipeline is the checkout.

    Raises:
        OAuthTokenError: If no token can be obtained.
        DocumentationPathError: If the folder of a set does not exist.
        DocServiceError: If the doc service cannot be reached or refuses the request.

    Returns:
        DocumentationValidationOutcome: The per-set outcomes, the flattened findings, and the
            rendered report.
    """
    access_token = fetch_client_credentials_token(token_uri, client_id, client_secret)

    outcomes = []
    for documentation_set in documentation_sets:
        outcomes.append(_validate_one(documentation_set, doc_service_url, access_token,
                                      working_directory))

    findings = [finding for outcome in outcomes for finding in findings_of(outcome)]
    return DocumentationValidationOutcome(
        sets=outcomes,
        findings=findings,
        report=_format_outcome_report(outcomes))


def _validate_one(documentation_set: DocumentationSet,
                  doc_service_url: str,
                  access_token: str,
                  working_directory: str) -> SetOutcome:
    """Walk, check and ask, for one documentation set."""
    root = documentation_set_root(documentation_set.path, working_directory)
    paths = collect_documentation_paths(root)

    content = None
    if documentation_set.source_format == "markdown":
        content = validate_documentation_content(root, paths)

    structure = validate_documentation_structure(doc_service_url, access_token, documentation_set,
                                                 paths)

    outcome = SetOutcome(documentation_set=documentation_set, structure=structure, content=content)
    return replace(outcome, report=format_set_report(outcome, len(paths)))


def format_set_report(outcome: SetOutcome, paths_walked: int,
                      heading: Optional[str] = None) -> str:
    """
    Render the report of one documentation set as the text a workflow prints.

    Args:
        outcome (SetOutcome): What both responsibilities said about the set.
        paths_walked (int): How many paths the pipeline found in the folder.
        heading (str, optional): The line the report opens with. The upload prints the findings of a
            set the doc service refused in this same layout, and says what it was doing rather than
            that it was validating.

    Returns:
        str: The report, plain text, with nothing specific to a pipeline platform in it.
    """
    documentation_set = outcome.documentation_set
    lines = [heading or f"Validating {documentation_set.describe()}"]

    if outcome.accepted:
        files = outcome.content.files_checked if outcome.content else 0
        lines.append(f"  {files} file(s) checked, {paths_walked} path(s), "
                     f"{outcome.structure.paths_ignored} ignored - "
                     f"{'content OK, ' if outcome.content else ''}structure OK")
        return "\n".join(lines) + "\n"

    if outcome.content is not None and not outcome.content.accepted:
        lines.append("")
        lines.append(f"  Content: {_problem_count(len(outcome.content.findings), outcome.content.findings_omitted)} "
                     f"in {outcome.content.files_checked} file(s).")
        lines.append("")
        for finding in outcome.content.findings:
            lines.extend(_finding_lines(f"{finding.path}:{finding.line}" if finding.line
                                        else finding.path,
                                        str(finding.code), finding.message))
        if outcome.content.findings_omitted:
            lines.append(f"      … and {outcome.content.findings_omitted} more, not listed.")

    structure = outcome.structure
    if not structure.accepted:
        lines.append("")
        lines.append(f"  Structure: {_problem_count(len(structure.findings), structure.findings_omitted)} "
                     f"in {structure.paths_checked} path(s), {structure.paths_ignored} ignored.")
        lines.append("")
        for finding in _structure_findings_in_print_order(structure):
            lines.extend(_finding_lines(finding.path or "(the documentation set)", finding.code,
                                        finding.message))
        if structure.findings_omitted:
            lines.append(f"      … and {structure.findings_omitted} more, not listed.")
        if structure.allowed_folders:
            lines.append("")
            lines.append(_wrapped_list("  Folders:   ", structure.allowed_folders))
        if structure.allowed_extensions:
            lines.append(_wrapped_list("  Extensions:",
                                       [f".{extension}" for extension in structure.allowed_extensions]))

    return "\n".join(lines) + "\n"


def _format_outcome_report(outcomes: Sequence[SetOutcome]) -> str:
    """Render every set's report, and the line that says how it ended."""
    report = "\n".join(outcome.report for outcome in outcomes)
    rejected = sum(1 for outcome in outcomes if not outcome.accepted)
    problems = sum(_problems_of(outcome) for outcome in outcomes)
    if rejected:
        report += (f"\nDocumentation validation failed: {problems} problem(s) in {rejected} of "
                   f"{len(outcomes)} documentation set(s).\n")
    else:
        report += (f"\nDocumentation validation passed: {len(outcomes)} documentation set(s).\n")
    return report


def _problems_of(outcome: SetOutcome) -> int:
    """How many problems one set has, both responsibilities together."""
    content = 0
    if outcome.content:
        content = len(outcome.content.findings) + outcome.content.findings_omitted
    return content + len(outcome.structure.findings) + outcome.structure.findings_omitted


def _problem_count(listed: int, omitted: int) -> str:
    """`3 problems`, and `3 of 8 problems` when the report was capped."""
    total = listed + omitted
    if omitted:
        return f"{listed} of {total} problem(s)"
    return f"{total} problem(s)"


def _structure_findings_in_print_order(structure: StructureReport) -> List:
    """Set-level findings first: an unknown template or an empty tree is about the whole set."""
    return ([finding for finding in structure.findings if not finding.path]
            + [finding for finding in structure.findings if finding.path])


def _finding_lines(where: str, code: str, message: str) -> List[str]:
    """
    One finding as the two-line block a report is made of.

    A code of a newer doc service can be wider than the column - the codes are its API and it may
    add one - so the column grows with it rather than letting the message start against it.
    """
    lines = [f"  {where}"]
    column = max(_CODE_WIDTH, len(code) + 2)
    indent = " " * (6 + column)
    wrapped = textwrap.wrap(message, width=max(_LINE_WIDTH - len(indent), _MIN_MESSAGE_WIDTH)) or [""]
    lines.append(f"      {code.ljust(column)}{wrapped[0]}")
    for continuation in wrapped[1:]:
        lines.append(f"{indent}{continuation}")
    return lines


def _wrapped_list(label: str, values: Sequence[str]) -> str:
    """A label and a comma-separated list, wrapped under the label."""
    indent = " " * (len(label) + 1)
    wrapped = textwrap.wrap(", ".join(values), width=_LINE_WIDTH - len(indent))
    return f"{label} " + f"\n{indent}".join(wrapped)


def findings_of(outcome: SetOutcome) -> List[Finding]:
    """
    Flatten the reports of one documentation set into the findings a pipeline annotates with.

    Args:
        outcome (SetOutcome): What was found about the set. The upload builds one carrying only the
            structure report, so a refused upload annotates the same way a refused validation does.

    Returns:
        List[Finding]: One finding per problem, each with its code, message, path and line.
    """
    findings = []
    if outcome.content:
        for finding in outcome.content.findings:
            findings.append(Finding(documentation_set=outcome.documentation_set.path,
                                    location="content",
                                    code=str(finding.code),
                                    message=finding.message,
                                    path=finding.path,
                                    line=finding.line))
    for finding in outcome.structure.findings:
        findings.append(Finding(documentation_set=outcome.documentation_set.path,
                                location="structure",
                                code=finding.code,
                                message=finding.message,
                                path=finding.path))
    return findings
