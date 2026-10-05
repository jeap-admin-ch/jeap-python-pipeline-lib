"""Shared CI-independent documentation inputs and version precedence."""
import json
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import subprocess

import pytest

from jeap_pipeline import (DocumentationConfigError, configured_documentation_sets,
                           documentation_commit_timestamp, documentation_pom_version,
                           documentation_versions, read_documentation_configuration_file)


@pytest.fixture(autouse=True)
def isolated_git_environment(monkeypatch):
    for name in list(os.environ):
        if name.startswith('GIT_'):
            monkeypatch.delenv(name)
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    monkeypatch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    for role in ('AUTHOR', 'COMMITTER'):
        monkeypatch.setenv(f'GIT_{role}_NAME', 'Test')
        monkeypatch.setenv(f'GIT_{role}_EMAIL', 'test@example.invalid')
        monkeypatch.setenv(f'GIT_{role}_DATE', '2026-10-06T12:00:00+00:00')


@pytest.fixture
def git_checkout(tmp_path, monkeypatch, isolated_git_environment):
    monkeypatch.chdir(tmp_path)
    subprocess.run(['git', 'init', '-q'], check=True)
    (tmp_path / 'f.txt').write_text('Not a timestamp\n', encoding='utf-8')
    subprocess.run(['git', 'add', 'f.txt'], check=True)
    subprocess.run(['git', 'commit', '-qm', 'test'], check=True)
    return tmp_path


def test_versions_resolve_project_only_once_and_only_when_needed():
    resolver = Mock(return_value="1.2.3")
    sets = [SimpleNamespace(type="system-docs", version=None, path="system"),
            SimpleNamespace(type="component-docs", version="2.0", path="component"),
            SimpleNamespace(type="library-docs", version=None, path="lib"),
            SimpleNamespace(type="library-docs", version=None, path="lib2")]
    assert documentation_versions(sets, "3.0", resolver) == {
        "component": "2.0", "lib": "3.0", "lib2": "3.0"}
    resolver.assert_not_called()
    assert documentation_versions(sets, project_version=resolver) == {
        "component": "2.0", "lib": "1.2.3", "lib2": "1.2.3"}
    resolver.assert_called_once_with()


def test_generated_docs_never_guess_a_project_version():
    resolver = Mock(side_effect=AssertionError("Must not resolve"))
    sets = [SimpleNamespace(type="component-docs", version=None, path="docs")]
    assert documentation_versions(sets, project_version=resolver, generated=True) == {}


def test_empty_project_version_is_resolved_only_once():
    resolver = Mock(return_value=None)
    sets = [SimpleNamespace(type='library-docs', version=None, path=f'lib{i}')
            for i in range(3)]
    assert documentation_versions(sets, project_version=resolver) == {}
    resolver.assert_called_once_with()


@pytest.mark.parametrize("xml", [
    "<project><parent><version>1</version></parent></project>",
    "<project><version>${revision}</version></project>", "<project>"])
def test_pom_refuses_inherited_unresolved_and_invalid_versions(tmp_path, xml):
    pom = tmp_path / "pom.xml"
    pom.write_text(xml)
    with pytest.raises(DocumentationConfigError):
        documentation_pom_version(str(pom))


@pytest.mark.parametrize("namespace", ["", ' xmlns="http://maven.apache.org/POM/4.0.0"'])
def test_literal_pom_version(tmp_path, namespace):
    pom = tmp_path / "pom.xml"
    pom.write_text(f"<project{namespace}><version> 1.2.3-SNAPSHOT </version></project>")
    assert documentation_pom_version(str(pom)) == "1.2.3-SNAPSHOT"


def test_missing_and_malformed_configuration(tmp_path):
    config = tmp_path / "docs.json"
    with pytest.raises(DocumentationConfigError, match="does not exist"):
        read_documentation_configuration_file(str(config))
    config.write_text("{")
    with pytest.raises(DocumentationConfigError, match="not valid JSON"):
        read_documentation_configuration_file(str(config))
    config.write_text(json.dumps({"docs": []}))
    assert read_documentation_configuration_file(str(config)) == {"docs": []}


def test_invalid_utf8_is_a_configuration_error(tmp_path):
    config = tmp_path / 'docs.json'
    config.write_bytes(b'{"label": "\xdcbersicht"}')
    with pytest.raises(DocumentationConfigError, match='not valid UTF-8') as refused:
        read_documentation_configuration_file(str(config))
    assert str(config) in str(refused.value)


@pytest.mark.parametrize("generated", [True, False])
def test_non_object_configuration_is_a_configuration_error(generated):
    with pytest.raises(DocumentationConfigError, match="object"):
        configured_documentation_sets([], "config.json", generated)


def test_commit_timestamp_comes_from_git(git_checkout):
    timestamp = documentation_commit_timestamp("HEAD")
    assert datetime.fromisoformat(timestamp.replace('Z', '+00:00')) == datetime(
        2026, 10, 6, 12, tzinfo=timezone.utc)
    with pytest.raises(DocumentationConfigError, match="commit date"):
        documentation_commit_timestamp("missing-revision")


def test_annotated_tag_returns_the_commit_timestamp(git_checkout, monkeypatch):
    monkeypatch.setenv('GIT_COMMITTER_DATE', '2026-10-07T12:00:00+00:00')
    subprocess.run(['git', 'tag', '-a', 'v1', '-m', 'release one'], check=True)
    timestamp = documentation_commit_timestamp('v1')
    assert datetime.fromisoformat(timestamp.replace('Z', '+00:00')) == datetime(
        2026, 10, 6, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('revision', ['HEAD:f.txt', 'HEAD^{tree}', 'HEAD..HEAD', '--all'])
def test_timestamp_rejects_non_commit_revisions(git_checkout, revision):
    with pytest.raises(DocumentationConfigError, match='commit date'):
        documentation_commit_timestamp(revision)


@pytest.mark.parametrize('existing', [False, True])
def test_revision_cannot_inject_an_output_option(git_checkout, existing):
    output = git_checkout / 'injected.txt'
    if existing:
        output.write_text('Keep this file', encoding='utf-8')
    with pytest.raises(DocumentationConfigError, match='commit date'):
        documentation_commit_timestamp('--output=injected.txt')
    if existing:
        assert output.read_text(encoding='utf-8') == 'Keep this file'
    else:
        assert not output.exists()


def test_git_error_preserves_stderr(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GIT_CEILING_DIRECTORIES', str(tmp_path.parent))
    result = subprocess.run(['git', 'rev-parse', '--verify', '--end-of-options', 'HEAD^{commit}'],
                            capture_output=True, text=True)
    assert result.returncode != 0
    with pytest.raises(DocumentationConfigError) as refused:
        documentation_commit_timestamp('HEAD')
    assert result.stderr.strip() in str(refused.value)
