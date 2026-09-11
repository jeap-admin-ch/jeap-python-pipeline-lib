"""Which branches of a repository publish its documentation.

Validating documentation and publishing it are two different questions: every push is validated, so
a mistake is reported to whoever made it, while publishing belongs to the line of development a team
calls current. By default that is the repository's default branch; a repository that publishes from
somewhere else - a documentation branch, or the throwaway branch of an end-to-end test - says which
branches in its documentation configuration, and that list replaces the default rule rather than
adding to it.

A pattern is a **branch glob**: `*` matches anything but a `/`, `**` matches across `/` as well,
`?` matches a single character that is not a `/`, and everything else matches itself. Which is also
what a push filter of a hosted pipeline means by it, so a list written for one reads the same here.

Nothing in this module knows which pipeline it runs in: what was pushed, the patterns and the
default branch all arrive as arguments, and where a platform keeps them is the caller's business.
"""

import re
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

from .doc_service_operations import PUBLISH_BRANCHES_KEY, DocumentationConfigError

#: The rule that decided, when the repository states no patterns.
RULE_DEFAULT_BRANCH = "default-branch"

#: The rule that decided, when the repository states patterns.
RULE_PUBLISH_BRANCHES = "publish-branches"

#: The rule that decided, when what was pushed is a tag.
RULE_TAG = "tag"

_HEADS_PREFIX = "refs/heads/"
_TAGS_PREFIX = "refs/tags/"


@dataclass(frozen=True)
class PublicationDecision:
    """
    Whether the documentation of a repository is published from what was pushed, and what decided.

    `reason` is a sentence for the person reading the pipeline's output: a run that publishes
    nothing has to say why, or the next question is why the site did not change.
    """

    publishes: bool
    branch: Optional[str]
    rule: str
    reason: str
    pattern: Optional[str] = None

    def __bool__(self) -> bool:
        """Whether the documentation is published, so the decision reads as the condition it is."""
        return self.publishes


def publish_branches_of(configuration: Any,
                        source: str = "the documentation configuration") -> Optional[List[str]]:
    """
    Read the branch patterns a repository states, if it states any.

    Args:
        configuration (Any): The parsed documentation configuration - the object
            `documentation_sets_from_config` reads the sets out of.
        source (str, optional): Where the configuration came from, for the error messages.

    Raises:
        DocumentationConfigError: If the key is not a list of non-empty strings, or is an empty
            list. An empty list is refused rather than read as *never publish*: turning publication
            off is the pipeline's own switch, and a list that lost its last entry is far more often
            a leftover than an intention.

    Returns:
        Optional[List[str]]: The patterns, or `None` when the repository states none - which means
            the default branch and nothing else.
    """
    if not isinstance(configuration, dict):
        raise DocumentationConfigError(
            f"{source} has to hold an object, not a {type(configuration).__name__}.")

    if PUBLISH_BRANCHES_KEY not in configuration:
        return None

    patterns = configuration[PUBLISH_BRANCHES_KEY]
    if not isinstance(patterns, list):
        raise DocumentationConfigError(
            f"{source}: '{PUBLISH_BRANCHES_KEY}' has to hold a list of branch patterns, not a "
            f"{type(patterns).__name__}.")
    if not patterns:
        raise DocumentationConfigError(
            f"{source}: '{PUBLISH_BRANCHES_KEY}' is empty. It says which branches publish the "
            f"documentation, so an empty list says nothing - remove the key to publish from the "
            f"default branch, or switch the upload off in the pipeline.")
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern.strip():
            raise DocumentationConfigError(
                f"{source}: '{PUBLISH_BRANCHES_KEY}' holds {pattern!r}, which is not a branch "
                f"pattern. Every entry is a branch name or a branch glob, written as a string.")
    return list(patterns)


def publishes_from(ref: str,
                   publish_branches: Optional[Sequence[str]] = None,
                   default_branch: Optional[str] = None) -> PublicationDecision:
    """
    Decide whether what was pushed publishes the documentation of the repository.

    The precedence is short and has no implicit half: a repository that states patterns publishes
    from the branches they match **and from nothing else**, and one that states none publishes from
    its default branch. A rule that were partly implicit is the one a reader gets wrong - stating
    `release/*` must not keep publishing from the default branch behind the author's back.

    A tag publishes nothing: documentation belongs to a line of development rather than to a release
    artifact. A tag is recognised when the full ref is given, so pass `refs/tags/...` or
    `refs/heads/...` where the pipeline has it and the bare branch name otherwise.

    Args:
        ref (str): What was pushed - a full ref (`refs/heads/master`, `refs/tags/v1.4.0`) or a
            branch name.
        publish_branches (Sequence[str], optional): The patterns of the repository, as
            `publish_branches_of` returns them. `None` means the repository states none.
        default_branch (str, optional): The default branch of the repository, which is what decides
            when there are no patterns.

    Raises:
        DocumentationConfigError: If `publish_branches` is an empty list.
        ValueError: If nothing can decide - no patterns and no default branch - or if no ref is
            given.

    Returns:
        PublicationDecision: Whether it publishes, which rule decided, and the sentence to print.
    """
    if not ref:
        raise ValueError("No ref given: which branch was pushed is what decides whether the "
                         "documentation is published.")

    if ref.startswith(_TAGS_PREFIX):
        tag = ref[len(_TAGS_PREFIX):]
        return PublicationDecision(
            publishes=False, branch=None, rule=RULE_TAG,
            reason=f"The tag '{tag}' publishes no documentation: documentation is published from a "
                   f"branch, so that it belongs to a line of development.")

    branch = ref[len(_HEADS_PREFIX):] if ref.startswith(_HEADS_PREFIX) else ref

    if publish_branches is not None and not publish_branches:
        raise DocumentationConfigError(
            "'publish-branches' is empty. It says which branches publish the documentation, so an "
            "empty list says nothing - state no patterns to publish from the default branch, or "
            "switch the upload off in the pipeline.")

    if publish_branches:
        for pattern in publish_branches:
            if branch_matches(branch, pattern):
                return PublicationDecision(
                    publishes=True, branch=branch, rule=RULE_PUBLISH_BRANCHES, pattern=pattern,
                    reason=f"The branch '{branch}' publishes the documentation: it matches "
                           f"'{pattern}' of 'publish-branches'.")
        return PublicationDecision(
            publishes=False, branch=branch, rule=RULE_PUBLISH_BRANCHES,
            reason=f"The branch '{branch}' publishes no documentation: 'publish-branches' names "
                   f"{_listed(publish_branches)}, and it matches none of them.")

    if not default_branch:
        raise ValueError(
            "Neither branch patterns nor a default branch were given, so nothing can decide "
            "whether the documentation is published. A repository that states no "
            "'publish-branches' publishes from its default branch, which the pipeline has to name.")

    if branch == default_branch:
        return PublicationDecision(
            publishes=True, branch=branch, rule=RULE_DEFAULT_BRANCH,
            reason=f"The branch '{branch}' publishes the documentation: it is the default branch "
                   f"of the repository.")

    return PublicationDecision(
        publishes=False, branch=branch, rule=RULE_DEFAULT_BRANCH,
        reason=f"The branch '{branch}' publishes no documentation: the documentation is published "
               f"from the default branch '{default_branch}'. State 'publish-branches' in the "
               f"documentation configuration to publish from other branches as well.")


def branch_matches(branch: str, pattern: str) -> bool:
    """
    Whether a branch name matches one branch glob.

    `*` matches anything but a `/`, `**` matches across `/` as well, `?` matches a single character
    that is not a `/`, and everything else matches itself - the semantics a push filter of a hosted
    pipeline gives the same list.

    Args:
        branch (str): The branch name, without `refs/heads/`.
        pattern (str): The glob, for instance `master`, `release/*` or `feature/**`.

    Returns:
        bool: Whether the glob matches the whole branch name.
    """
    return re.fullmatch(_expression_of(pattern), branch) is not None


def _expression_of(pattern: str) -> str:
    """
    Translate a branch glob into an anchored regular expression.

    Deliberately not `fnmatch`, whose `*` crosses a `/`: `release/*` would then match
    `release/1.2/hotfix`, which is not what a list of branch globs means anywhere else.
    """
    expression = []
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if pattern.startswith("**", index):
                expression.append(".*")
                index += 2
                continue
            expression.append("[^/]*")
        elif character == "?":
            expression.append("[^/]")
        else:
            expression.append(re.escape(character))
        index += 1
    return "".join(expression)


def _listed(patterns: Sequence[str]) -> str:
    """The patterns as a person reads them out."""
    return ", ".join(f"'{pattern}'" for pattern in patterns)
