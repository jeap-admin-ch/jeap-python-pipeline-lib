"""Real-tool tests: install the documented Node packages and put Pandoc on PATH (or set PANDOC)."""

import os
import pytest

from jeap_pipeline import (DocumentationConversionError, convert_asciidoc,
                           validate_documentation_content)


@pytest.fixture
def convert(tmp_path):
    source = tmp_path / "input"
    source.mkdir()

    def run(text, extras=None):
        (source / "all-docs.adoc").write_text(text, encoding="utf-8")
        for name, content in (extras or {}).items():
            file = source / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content, encoding="utf-8")
        output = tmp_path / "output"
        names = convert_asciidoc(str(source), str(output), pandoc=os.getenv("PANDOC", "pandoc"))
        assert validate_documentation_content(str(output), names).accepted
        return {name: (output / name).read_text(encoding="utf-8") for name in names}

    return run


def test_modulith_canvas_and_c4_diagram(convert):
    diagram = "@startuml\n!include <C4/C4_Component>\nComponent(inventory, \"Inventory\")\n@enduml"
    pages = convert("== Application\nplantuml::components.puml[]\n\n"
                    "== Inventory\ninclude::module-inventory.adoc[]\n", {
                        "components.puml": diagram,
                        "module-inventory.adoc": "[%autowidth.stretch, cols=\"h,a\"]\n|===\n"
                        "|Base package\n|`example.inventory`\n|Events listened to\n"
                        "|* `example.OrderCompleted` (async)\n|===\n"})
    assert set(pages) == {"modulith-application.md", "modulith-inventory.md"}
    assert diagram in pages["modulith-application.md"]
    inventory = pages["modulith-inventory.md"]
    assert "**Events listened to**" in inventory
    assert "- `example.OrderCompleted` (async)" in inventory
    assert "`example.inventory`" in inventory
    assert "<table" not in inventory
    assert "JEAPDIAGRAM" not in "".join(pages.values())


def test_nested_include_and_cross_page_reference(convert):
    pages = convert("== Application\nSee <<_inventory,inventory>>.\n\n"
                    "include::sections/inventory.adoc[]\n", {
                        "sections/inventory.adoc": "== Inventory\ninclude::details.adoc[]\n",
                        "sections/details.adoc": "Stores stock.\n"})
    assert "[inventory](modulith-inventory.md#inventory)" in pages["modulith-application.md"]
    assert "Stores stock." in pages["modulith-inventory.md"]


@pytest.mark.parametrize("text", [
    "== Application\ninclude::missing.adoc[]\n",
    "== Application\nplantuml::missing.puml[]\n",
    "== Application\ninclude::../outside.adoc[]\n",
    "== Duplicate\nOne\n\n== Duplicate!\nTwo\n",
])
def test_invalid_input_is_not_silently_published(convert, text):
    with pytest.raises(DocumentationConversionError):
        convert(text)


def test_missing_include_names_the_missing_file(convert):
    with pytest.raises(DocumentationConversionError, match="missing.adoc"):
        convert("== Application\ninclude::missing.adoc[]\n")


def test_simple_table_stays_markdown(convert):
    page = convert("== Values\n\n|===\n|Name |Value\n\n|one |two\n|===\n")["modulith-values.md"]
    assert "one" in page and "two" in page
    assert "|" in page
    assert "<table" not in page


def test_complex_table_caption_and_multiple_paragraphs_are_preserved(convert):
    page = convert("== Application\n\n.Canvas\n[cols=\"h,a\"]\n|===\n"
                   "|Description\n|First paragraph.\n\nSecond paragraph.\n|===\n")["modulith-application.md"]
    assert "Canvas" in page
    assert "First paragraph." in page and "Second paragraph." in page
    assert "<table" not in page


def test_heading_punctuation_uses_rendered_anchor(convert):
    pages = convert("== Application\nSee <<_version_1_0,version>>.\n\n== Version 1.0\nDetails\n")
    assert "modulith-version-1-0.md#version-10" in pages["modulith-application.md"]


def test_code_fence_heading_does_not_split_pages(convert):
    pages = convert("== Application\n\n[source,markdown]\n----\n# Not a page\n----\n")
    assert list(pages) == ["modulith-application.md"]
    assert "# Not a page" in pages["modulith-application.md"]


def test_missing_tool_has_actionable_error(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (source / "all-docs.adoc").write_text("== Application\nText\n")
    with pytest.raises(DocumentationConversionError, match="Cannot run missing-node"):
        convert_asciidoc(str(source), str(tmp_path / "output"), node="missing-node")


def test_existing_output_is_not_overwritten(tmp_path):
    (tmp_path / "all-docs.adoc").write_text("Text")
    with pytest.raises(DocumentationConversionError, match="overlap"):
        convert_asciidoc(str(tmp_path), str(tmp_path / "output"))


def test_local_asset_copied_and_link_rewritten(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (source / "all-docs.adoc").write_text("== Application\n\nimage::logo.svg[Logo]\n")
    (source / "logo.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    target = tmp_path / "output"
    convert_asciidoc(str(source), str(target), pandoc=os.getenv("PANDOC", "pandoc"))
    assert (target / "assets/logo.svg").read_bytes() == (source / "logo.svg").read_bytes()
    assert "assets/logo.svg" in (target / "modulith-application.md").read_text()


def test_symlink_include_not_followed(tmp_path):
    source = tmp_path / "input"
    source.mkdir()
    (tmp_path / "secret.adoc").write_text("PRIVATE")
    (source / "link.adoc").symlink_to(tmp_path / "secret.adoc")
    (source / "all-docs.adoc").write_text("== Application\ninclude::link.adoc[]\n")
    with pytest.raises(DocumentationConversionError):
        convert_asciidoc(str(source), str(tmp_path / "output"), pandoc=os.getenv("PANDOC", "pandoc"))
