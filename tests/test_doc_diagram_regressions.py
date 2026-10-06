"""Compatibility and pipeline boundary regressions for the diagram check."""

import os
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jeap_pipeline.doc_conversion import DocumentationConversionError
from jeap_pipeline.doc_diagram_sources import check_diagram_sources, diagram_pairs_of
from jeap_pipeline.doc_path_tree import collect_documentation_paths
from jeap_pipeline.doc_preparation import prepare_documentation_config
from jeap_pipeline.doc_service_operations import DocumentationSet
from jeap_pipeline.doc_upload import _prepare, UploadProvenance
from jeap_pipeline.doc_validation import SetOutcome, _validate_one


def git(repo, *args, date="2026-01-01T12:00:00Z"):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env={**os.environ, "GIT_AUTHOR_DATE": date,
                                          "GIT_COMMITTER_DATE": date}).stdout.strip()


def commit(repo, message, date="2026-01-01T12:00:00Z"):
    git(repo, "add", ".")
    git(repo, "-c", "user.name=Test", "-c", "user.email=test@example.org",
        "commit", "-qm", message, date=date)


def diagram_repo(tmp_path):
    repo = tmp_path / "repo"
    docs = repo / "docs"
    docs.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    (docs / "overview.drawio").write_text("original")
    (docs / "overview.svg").write_text("<svg/>")
    (docs / "all-docs.adoc").write_text("= Overview\n\nimage::overview.svg[]\n")
    commit(repo, "paired")
    (docs / "overview.drawio").write_text("changed")
    commit(repo, "forgot export", "2026-01-02T12:00:00Z")
    return repo, docs


def test_positional_set_outcome_remains_compatible():
    outcome = SetOutcome(None, SimpleNamespace(accepted=True), None, "existing report")
    assert outcome.report == "existing report"
    assert outcome.diagrams is None
    assert outcome.accepted


def test_html_assets_survive_collection_and_validation(tmp_path):
    paths = ["overview.html", "overview.css", "overview.js", "overview.svg", "overview.woff2"]
    for path in paths:
        (tmp_path / path).write_text("content")
    assert collect_documentation_paths(str(tmp_path), source_format="html") == sorted(paths)
    assert diagram_pairs_of(paths, source_format="html") == []
    doc = DocumentationSet(path=".", type="component-docs", system="test",
                           component="demo", template="arc42", source_format="html",
                           location="5-building-block-view", topic="api", label="API")
    with patch("jeap_pipeline.doc_validation.validate_documentation_structure",
               return_value=SimpleNamespace(accepted=True, paths_ignored=0)) as structure:
        result = _validate_one(doc, "https://unused", "token", str(tmp_path))
    assert result.accepted
    assert structure.call_args.args[3] == sorted(paths)
    provenance = UploadProvenance("https://example.org/repo", "abc", "main", "2026-01-01T12:00:00Z")
    prepared = _prepare(doc, provenance, "1.0.0", None, "test", str(tmp_path))
    assert prepared[-1] == sorted(paths)


def test_asciidoc_checks_original_history_before_starting_tools(tmp_path):
    repo, docs = diagram_repo(tmp_path)
    config = {"system": "test", "docs": [{"path": "docs", "type": "system-docs",
              "template": "arc42", "source-format": "asciidoc", "location": "5-building-block-view"}]}
    with patch("jeap_pipeline.doc_conversion._run") as tool:
        with pytest.raises(DocumentationConversionError, match="STALE_DIAGRAM_IMAGE"):
            prepare_documentation_config(config, "converted", str(repo))
    tool.assert_not_called()
    assert not (repo / "converted").exists()


def test_asciidoc_entry_is_not_mistaken_for_diagram_source():
    assert diagram_pairs_of(["overview.adoc", "overview.svg", "overview.drawio"],
                            source_format="asciidoc")[0].source == "overview.drawio"


def test_shallow_asciidoc_input_is_deepened_before_rejecting_stale_export(tmp_path):
    repo, _ = diagram_repo(tmp_path)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", repo.as_uri(), str(clone)], check=True)
    config = {"system": "test", "docs": [{"path": "docs", "type": "system-docs",
              "template": "arc42", "source-format": "asciidoc", "location": "5-building-block-view"}]}
    with patch("jeap_pipeline.doc_conversion._run") as tool:
        with pytest.raises(DocumentationConversionError, match="STALE_DIAGRAM_IMAGE"):
            prepare_documentation_config(config, "converted", str(clone), deepen_diagram_history=True)
    tool.assert_not_called()
    assert git(clone, "rev-parse", "--is-shallow-repository") == "false"


def test_reexported_asciidoc_diagram_converts_and_publishes_only_image(tmp_path):
    repo, docs = diagram_repo(tmp_path)
    (docs / "overview.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>updated</text></svg>')
    commit(repo, "export updated", "2026-01-03T12:00:00Z")
    config = {"system": "test", "docs": [{"path": "docs", "type": "system-docs",
              "template": "arc42", "source-format": "asciidoc", "location": "5-building-block-view"}]}
    prepared = prepare_documentation_config(config, "converted", str(repo),
                                             pandoc=os.getenv("PANDOC", "pandoc"))
    root = repo / prepared["docs"][0]["path"]
    assert list(root.rglob("overview.svg"))
    assert not list(root.rglob("*.drawio"))
    assert list(root.rglob("*.md"))


def test_generated_asciidoc_explicitly_skips_committed_history_check(tmp_path):
    config = {"generated-docs": [{"system": "test", "path": "target/docs", "type": "system-docs",
              "template": "arc42", "source-format": "asciidoc", "location": "5-building-block-view"}]}
    with patch("jeap_pipeline.doc_preparation.convert_asciidoc") as convert:
        prepare_documentation_config(config, "converted", str(tmp_path), deepen_diagram_history=True)
    assert convert.call_args.kwargs == {"deepen_diagram_history": True,
                                       "check_committed_diagrams": False}


def test_shallow_linked_worktree_is_detected_and_deepened(tmp_path):
    repo, _ = diagram_repo(tmp_path)
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", "--depth", "1", repo.as_uri(), str(clone)], check=True)
    worktree = tmp_path / "linked"
    git(clone, "worktree", "add", "--detach", str(worktree), "HEAD")
    root = str(worktree / "docs")
    paths = collect_documentation_paths(root, keep_diagram_sources=True)
    report = check_diagram_sources(root, paths)
    assert str(report.findings[0].code) == "UNDATABLE_DIAGRAM_HISTORY"
    report = check_diagram_sources(root, paths, deepen=True)
    assert str(report.findings[0].code) == "STALE_DIAGRAM_IMAGE"
