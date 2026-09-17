import copy
import os

import pytest

from jeap_pipeline import (DocumentationConfigError, documentation_sets_from_config,
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
