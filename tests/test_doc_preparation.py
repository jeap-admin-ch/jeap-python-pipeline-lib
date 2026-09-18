import copy
import os

import pytest

from jeap_pipeline import (DocumentationConfigError, DocumentationPathError,
                           documentation_sets_from_config, documentation_sets_from_entries,
                           prepare_documentation_config, requires_asciidoc_conversion)


def configuration():
    return {"system": "orders", "component": "orders-service", "version": "1.2.3",
            "publish-branches": ["master"], "docs": [{"path": "input", "type": "component-docs",
            "template": "arc42", "source-format": "asciidoc", "location": "5-building-block-view"}]}


def test_prepared_configuration_uses_only_wire_contract(tmp_path):
    original = configuration()
    saved = copy.deepcopy(original)
    (tmp_path / "input").mkdir()
    (tmp_path / "input/all-docs.adoc").write_text("== Application\nText\n")
    result = prepare_documentation_config(original, "prepared", str(tmp_path),
                                          pandoc=os.getenv("PANDOC", "pandoc"))
    document = documentation_sets_from_config(result)[0]
    assert document.path == "prepared/set-0"
    assert document.validation_query_parameters() == {
        "system": "orders", "component": "orders-service", "type": "component-docs",
        "template": "arc42", "source-format": "markdown"}
    assert document.version == "1.2.3"
    assert result["publish-branches"] == ["master"]
    assert original == saved
    assert (tmp_path / "prepared/set-0/5-building-block-view/modulith-application.md").exists()


def test_unconverted_input_cannot_reach_upload_contract():
    with pytest.raises(DocumentationConfigError):
        documentation_sets_from_config(configuration())


def test_collision_with_handwritten_markdown_is_rejected():
    config = configuration()
    config["docs"].append({"path": "docs", "type": "component-docs", "template": "arc42",
                           "source-format": "markdown"})
    with pytest.raises(DocumentationConfigError, match="same documentation set"):
        requires_asciidoc_conversion(config)


@pytest.mark.parametrize("key,value", [("entry", "../outside.adoc"), ("entry", 3),
                                      ("location", "../outside"), ("topic", "modules"),
                                      ("typo", "wrong")])
def test_invalid_conversion_options_rejected(key, value):
    config = configuration()
    config["docs"][0][key] = value
    with pytest.raises(DocumentationConfigError):
        requires_asciidoc_conversion(config)


def test_markdown_passes_through_without_tools(tmp_path):
    config = configuration()
    config["docs"][0]["source-format"] = "markdown"
    del config["docs"][0]["location"]
    assert not requires_asciidoc_conversion(config)
    assert prepare_documentation_config(config, "prepared", str(tmp_path), node="missing") == config


def test_output_must_not_overwrite_input(tmp_path):
    with pytest.raises(DocumentationConfigError, match="overlap"):
        prepare_documentation_config(configuration(), "input", str(tmp_path))


def build_configuration():
    return {"generated-docs": [dict(configuration()["docs"][0], system="orders",
                                    component="orders-service")],
            "branch": {"feature": {"uploadGeneratedDocs": False}},
            "docker": {"imagesToBuild": [{"imageRepositoryName": "orders"}]}}


def test_build_converts_per_subject_and_preserves_html_and_pipeline_settings(tmp_path):
    config = build_configuration()
    config["generated-docs"].extend([
        {"path": "html", "type": "component-docs", "system": "orders", "component": "orders-service",
         "template": "arc42", "source-format": "html", "location": "5-building-block-view",
         "topic": "javadoc", "label": "Javadoc"},
        dict(config["generated-docs"][0], path="library", type="library-docs", component=None,
             library="orders-common")])
    saved = copy.deepcopy(config)
    for name in ("input", "library"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "all-docs.adoc").write_text("== Application\nText\n")
    assert requires_asciidoc_conversion(config)
    prepared = prepare_documentation_config(config, "prepared", str(tmp_path),
                                             pandoc=os.getenv("PANDOC", "pandoc"))
    component, html, library = documentation_sets_from_entries(prepared["generated-docs"])
    assert component.path == "prepared/set-0"
    assert component.component == "orders-service"
    assert component.source_format == library.source_format == "markdown"
    assert component.location is None and component.version is None
    assert library.path == "prepared/set-2" and library.library == "orders-common"
    assert html.path == "html" and html.source_format == "html"
    assert prepared["generated-docs"][1] == saved["generated-docs"][1]
    assert prepared["branch"] == saved["branch"] and prepared["docker"] == saved["docker"]
    assert config == saved
    assert (tmp_path / library.path / "5-building-block-view/modulith-application.md").exists()


@pytest.mark.parametrize("key,value", [("version", "1.0.0"), ("site", "handbook"),
                                      ("publish-branches", ["master"]), ("typo", "wrong"),
                                      ("entry", "../outside.adoc"), ("location", "../outside")])
def test_build_preparation_retains_generated_entry_rules(key, value):
    config = build_configuration()
    config["generated-docs"][0][key] = value
    with pytest.raises(DocumentationConfigError, match="generated-docs"):
        requires_asciidoc_conversion(config)


def test_build_collisions_are_checked_after_conversion():
    config = build_configuration()
    config["generated-docs"].append(dict(config["generated-docs"][0], path="other",
                                         location="6-runtime-view"))
    with pytest.raises(DocumentationConfigError, match="replace"):
        requires_asciidoc_conversion(config)


def test_build_inspection_needs_no_generated_files_but_conversion_does(tmp_path):
    config = build_configuration()
    assert requires_asciidoc_conversion(config)
    with pytest.raises(DocumentationPathError, match="input"):
        prepare_documentation_config(config, "prepared", str(tmp_path))
    assert not (tmp_path / "prepared").exists()


def test_build_markdown_passes_through_without_tools(tmp_path):
    config = build_configuration()
    config["generated-docs"][0]["source-format"] = "markdown"
    del config["generated-docs"][0]["location"]
    assert not requires_asciidoc_conversion(config)
    assert prepare_documentation_config(config, "prepared", str(tmp_path), node="missing") == config


@pytest.mark.parametrize("config", [None, [], {}, {"generated-docs": []}, {"generated-docs": "input"}])
def test_invalid_build_configuration_is_refused(config):
    with pytest.raises(DocumentationConfigError):
        requires_asciidoc_conversion(config)


@pytest.mark.parametrize("config", [
    {}, {"branch": {}},
    dict(configuration(), **{"generated-docs": []}),
    dict(build_configuration(), docs=None),
])
def test_missing_or_ambiguous_layout_is_refused_by_both_entry_points(config, tmp_path):
    with pytest.raises(DocumentationConfigError, match="exactly one"):
        requires_asciidoc_conversion(config)
    with pytest.raises(DocumentationConfigError, match="exactly one"):
        prepare_documentation_config(config, "prepared", str(tmp_path), node="missing")
    assert not (tmp_path / "prepared").exists()
