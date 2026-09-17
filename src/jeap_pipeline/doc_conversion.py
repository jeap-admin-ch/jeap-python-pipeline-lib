"""Convert AsciiDoc into publishable Markdown using Asciidoctor and Pandoc.

Tools are supplied by the caller. No downloads or GitHub-specific environment are used here.
"""

import copy
import json
import re
import shutil
import subprocess
import tempfile
from importlib.resources import files
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from markdown_it import MarkdownIt

from .doc_path_tree import collect_documentation_paths


class DocumentationConversionError(ValueError):
    """An input or a conversion tool could not produce publishable documentation."""


def convert_asciidoc(input_directory: str, output_directory: str,
                     entry: str = "all-docs.adoc", node: str = "node",
                     pandoc: str = "pandoc") -> list[str]:
    """Convert an entry document to Markdown pages in an empty output directory.

    Top-level sections become pages. Complex two-column canvases become labelled sections;
    simple tables stay tables. Local assets are copied, diagrams become PlantUML fences.
    The caller places this directory in the target chapter and validates the resulting set.
    """
    source = Path(input_directory).resolve()
    target = Path(output_directory).resolve()
    if source == target or source in target.parents or target in source.parents:
        raise DocumentationConversionError("Input and output directories must not overlap.")
    entry_path = Path(entry)
    if entry_path.is_absolute() or ".." in entry_path.parts or "\\" in entry:
        raise DocumentationConversionError("'entry' must be a relative path inside the input directory.")
    paths = collect_documentation_paths(str(source))
    if entry not in paths:
        raise DocumentationConversionError(f"Entry document not found: {source / entry}")
    if target.exists() and any(target.iterdir()):
        raise DocumentationConversionError(f"Output directory must be empty: {target}")

    # A snapshot excludes symlinks and lets Asciidoctor's safe mode confine includes to the input.
    with tempfile.TemporaryDirectory(prefix="jeap-asciidoc-") as temporary:
        snapshot = Path(temporary) / "input"
        for path in paths:
            destination = snapshot / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / path, destination)
        bridge = files("jeap_pipeline").joinpath("asciidoc_bridge.cjs")
        try:
            converted = json.loads(_run([node, str(bridge), str(snapshot), entry]))
        except DocumentationConversionError as error:
            raise DocumentationConversionError(str(error).replace(str(snapshot), str(source))) from error
        document = ET.fromstring(converted["docbook"])
        _normalize_canvases(document)
        ast = json.loads(_run([pandoc, "--from=docbook", "--to=json"],
                              ET.tostring(document, encoding="unicode")))
        ast = _flatten_figures(ast)
        diagrams = {diagram["token"]: diagram["source"] for diagram in converted["diagrams"]}
        _restore_diagrams(ast, diagrams)
        pages = _split_pages(ast)
        _resolve_links_and_assets(pages, snapshot, target)
        rendered = {}
        for name, title, blocks in pages:
            page = dict(ast, blocks=blocks)
            markdown = _run([pandoc, "--from=json", "--to=gfm", "--wrap=none"], json.dumps(page))
            _check_no_raw_html(markdown, name)
            rendered[name] = f"---\ntitle: {json.dumps(title, ensure_ascii=False)}\n---\n\n{markdown}"
        target.mkdir(parents=True, exist_ok=True)
        for name, markdown in rendered.items():
            (target / name).write_text(markdown, encoding="utf-8")
    return sorted(rendered)


def _run(command, content=None):
    try:
        result = subprocess.run(command, input=content, capture_output=True, text=True,
                                encoding="utf-8", timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DocumentationConversionError(f"Cannot run {command[0]}: {error}") from error
    if result.returncode:
        raise DocumentationConversionError(f"{command[0]} failed: {result.stderr.strip()}")
    return result.stdout


def _local_name(element):
    return element.tag.rsplit("}", 1)[-1]


def _normalize_canvases(document):
    """Expand block-valued two-column tables before Pandoc can turn them into raw HTML."""
    for parent in list(document.iter()):
        for table in list(parent):
            if _local_name(table) not in ("table", "informaltable"):
                continue
            complex_cells = any(_local_name(node) in ("itemizedlist", "orderedlist", "programlisting")
                                for node in table.iter())
            # Modulith marks the first column as a row header, including canvases with only scalars.
            rows = [node for node in table.iter() if _local_name(node) == "row"]
            entries = [[cell for cell in row if _local_name(cell) == "entry"] for row in rows]
            complex_cells = complex_cells or any(len(cell) > 1 for row in entries for cell in row)
            canvas = bool(entries) and all(
                any(_local_name(node) == "emphasis" and node.get("role") == "strong"
                    for node in row[0].iter()) for row in entries if row)
            if not complex_cells and not canvas:
                continue
            if any(len(row) != 2 for row in entries):
                raise DocumentationConversionError(
                    "A complex table has more than two columns. Use simple cells or a two-column canvas.")
            if any(cell.get(key) for row in entries for cell in row
                   for key in ("namest", "nameend", "morerows")):
                raise DocumentationConversionError("Spanning cells in complex tables are not supported.")
            replacement = []
            caption = next((child for child in table if _local_name(child) == "title"), None)
            if caption is not None:
                paragraph = ET.Element("para")
                paragraph.text = "".join(caption.itertext())
                replacement.append(paragraph)
            for label, content in entries:
                para = ET.Element("para")
                emphasis = ET.SubElement(para, "emphasis", {"role": "bold"})
                emphasis.text = "".join(label.itertext()).strip()
                replacement.append(para)
                if content.text and content.text.strip():
                    value = ET.Element("para")
                    value.text = content.text
                    replacement.append(value)
                replacement.extend(copy.deepcopy(list(content)))
            position = list(parent).index(table)
            parent.remove(table)
            for offset, node in enumerate(replacement):
                parent.insert(position + offset, node)


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _flatten_figures(value):
    """GFM writes Figure nodes as HTML; images and their caption blocks work as Markdown."""
    if isinstance(value, dict):
        return {key: _flatten_figures(child) for key, child in value.items()}
    if isinstance(value, list):
        flattened = []
        for child in value:
            if isinstance(child, dict) and child.get("t") == "Figure":
                _, caption, body = child["c"]
                flattened.extend(_flatten_figures(body + caption[1]))
            else:
                flattened.append(_flatten_figures(child))
        return flattened
    return value


def _restore_diagrams(ast, diagrams):
    seen = set()
    for node in _walk(ast):
        if node.get("t") == "Para" and len(node["c"]) == 1:
            inline = node["c"][0]
            token = inline.get("c") if inline.get("t") == "Str" else None
            if token in diagrams:
                node.update(t="CodeBlock", c=[["", ["plantuml"], []], diagrams[token].strip()])
                seen.add(token)
    if seen != diagrams.keys():
        raise DocumentationConversionError("A PlantUML placeholder was lost during conversion.")


def _text(inlines):
    parts = []
    for node in _walk(inlines):
        kind = node.get("t")
        if kind == "Str":
            parts.append(node["c"])
        elif kind == "Code":
            parts.append(node["c"][1])
        elif kind in ("Space", "SoftBreak", "LineBreak"):
            parts.append(" ")
    return "".join(parts)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "page"


def _split_pages(ast):
    blocks = ast["blocks"]
    levels = [block["c"][0] for block in blocks if block.get("t") == "Header"]
    level = min(levels) if levels else 1
    pages = []
    current = []
    title = "Application"
    for block in blocks:
        if block.get("t") == "Header" and block["c"][0] == level:
            if current:
                pages.append((f"modulith-{_slug(title)}.md", title, current))
            title = _text(block["c"][2])
            current = []
        if block.get("t") == "Header":
            block["c"][0] = max(1, block["c"][0] - level + 1)
        current.append(block)
    if current:
        pages.append((f"modulith-{_slug(title)}.md", title, current))
    if not pages:
        raise DocumentationConversionError("The entry document contains no publishable content.")
    names = [name for name, _, _ in pages]
    if len(set(names)) != len(names):
        raise DocumentationConversionError("Top-level headings produce duplicate page names.")
    return pages


def _resolve_links_and_assets(pages, source, target):
    anchors = {}
    for name, _, blocks in pages:
        used = {}
        for node in _walk(blocks):
            if node.get("t") == "Header":
                identifier = node["c"][1][0]
                anchor = re.sub(r"[^\w\- ]", "", _text(node["c"][2]).lower()).replace(" ", "-")
                count = used.get(anchor, 0)
                used[anchor] = count + 1
                anchors[identifier] = (name, anchor + (f"-{count}" if count else ""))
    assets = {}
    for name, _, blocks in pages:
        for node in _walk(blocks):
            if node.get("t") not in ("Link", "Image"):
                continue
            reference = node["c"][-1][0]
            url = urlsplit(reference)
            if url.scheme or url.netloc or reference.startswith("/"):
                continue
            if not url.path and url.fragment:
                if url.fragment in anchors:
                    page, anchor = anchors[url.fragment]
                    node["c"][-1][0] = f"{page}#{anchor}" if page != name else f"#{anchor}"
                continue
            path = unquote(url.path)
            asset = (source / path).resolve()
            if not asset.is_relative_to(source) or not asset.is_file():
                raise DocumentationConversionError(f"Local link or image does not exist in the input: {reference}")
            if asset.suffix.lower() in (".adoc", ".asciidoc", ".puml"):
                raise DocumentationConversionError(
                    f"Link to source file {reference}: use an AsciiDoc cross-reference to a section instead.")
            destination = "assets/" + asset.relative_to(source).as_posix()
            node["c"][-1][0] = destination + (f"#{url.fragment}" if url.fragment else "")
            assets[destination] = asset
    for destination, asset in assets.items():
        path = target / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(asset, path)


def _check_no_raw_html(markdown, name):
    """The target site escapes HTML, so a successful conversion must not rely on it."""
    for token in MarkdownIt("commonmark").parse(markdown):
        if token.type == "html_block" or any(child.type == "html_inline" for child in token.children or []):
            raise DocumentationConversionError(
                f"{name} needs raw HTML after conversion. Simplify the table or markup; "
                "the Doc Service displays HTML as text.")
