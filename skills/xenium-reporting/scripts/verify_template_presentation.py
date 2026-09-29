#!/usr/bin/env python3
"""Verify a template presentation against its saved content and asset inputs.

Standard library only. This checks OOXML, direct image byte equality and planned
timing; it does not claim visual fidelity, text fit or rehearsed talk duration.
Relative figure paths resolve from the spec; template paths from the profile;
manifest source paths from the manifest. Slide numbers are one-based.
"""

from __future__ import annotations

import argparse
import json
import math
import posixpath
import struct
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"p": P, "a": A, "r": R}
SOURCE_HEADER = "Sources (reference only):"


class ValidationError(ValueError):
    """An input or package cannot be interpreted by this verifier."""


class Receipt:
    def __init__(self, inputs: dict):
        self.data = {
            "schemaVersion": 1,
            "status": "failed",
            "inputs": inputs,
            "checks": [],
            "limitations": [
                "These checks do not establish visual template fidelity, text fit, or readability.",
                "Rendering/layout checks and opening the file in PowerPoint are separate evidence.",
                "Duration is the saved speaking-time plan, not a rehearsed or measured duration.",
                "Figure identity uses direct byte comparison; no checksums are computed.",
            ],
        }

    def check(self, name: str, ok: bool, **evidence) -> bool:
        self.data["checks"].append({"name": name, "status": "passed" if ok else "failed", **evidence})
        return bool(ok)

    def finish(self) -> bool:
        checks = self.data["checks"]
        passed = bool(checks) and all(c["status"] == "passed" for c in checks)
        self.data["status"] = "passed" if passed else "failed"
        self.data["passedChecks"] = sum(c["status"] == "passed" for c in checks)
        self.data["failedChecks"] = sum(c["status"] == "failed" for c in checks)
        return passed


def read_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValidationError(f"Expected a JSON object: {path}")
    return obj


def resolve_input(base: Path, value: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValidationError("Input paths must be nonempty strings")
    path = Path(value).expanduser()
    return (path if path.is_absolute() else base.parent / path).resolve()


def number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def require(condition: bool, message: str):
    if not condition:
        raise ValidationError(message)


def normalized_text(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def paragraph_text(paragraph: ET.Element) -> str:
    chunks = []
    for node in paragraph.iter():
        if node.tag == f"{{{A}}}t":
            chunks.append(node.text or "")
        elif node.tag == f"{{{A}}}br":
            chunks.append("\n")
    return normalized_text("".join(chunks))


def body_text(body: ET.Element) -> str:
    return "\n".join(paragraph_text(p) for p in body.findall("a:p", NS))


def text_shapes(root: ET.Element) -> list[str]:
    return [body_text(body) for body in root.findall(".//p:sp/p:txBody", NS)]


def native_tables(root: ET.Element) -> list[list[list[str]]]:
    return [
        [
            [body_text(cell.find("a:txBody", NS)) if cell.find("a:txBody", NS) is not None else ""
             for cell in row.findall("a:tc", NS)]
            for row in table.findall("a:tr", NS)
        ]
        for table in root.findall(".//a:tbl", NS)
    ]


class Package:
    def __init__(self, path: Path):
        self.path = path
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            require(len(names) == len(set(names)), f"Duplicate ZIP members: {path}")
            self.parts = {name: archive.read(name) for name in names if not name.endswith("/")}
        self.xml_cache = {}

    def xml(self, name: str) -> ET.Element:
        if name not in self.parts:
            raise ValidationError(f"Missing package part: {name}")
        if name not in self.xml_cache:
            self.xml_cache[name] = ET.fromstring(self.parts[name])
        return self.xml_cache[name]

    @staticmethod
    def rels_name(part: str) -> str:
        if not part:
            return "_rels/.rels"
        folder, name = posixpath.split(part)
        return posixpath.join(folder, "_rels", name + ".rels")

    @staticmethod
    def source_part(rels_name: str) -> str:
        if rels_name == "_rels/.rels":
            return ""
        folder, filename = posixpath.split(rels_name)
        require(posixpath.basename(folder) == "_rels" and filename.endswith(".rels"),
                f"Invalid relationship part name: {rels_name}")
        return posixpath.join(posixpath.dirname(folder), filename[:-5])

    @staticmethod
    def target(source: str, target: str) -> str:
        parsed = urlsplit(target)
        require(not parsed.scheme and not parsed.netloc,
                f"Internal relationship has a remote target: {target}")
        path = unquote(parsed.path)
        if not path:
            return source
        resolved = posixpath.normpath(path.lstrip("/") if path.startswith("/")
                                     else posixpath.join(posixpath.dirname(source), path))
        require(resolved != ".." and not resolved.startswith("../"),
                f"Relationship escapes package: {target}")
        return resolved

    def rels(self, part: str) -> dict[str, dict]:
        name = self.rels_name(part)
        if name not in self.parts:
            return {}
        result = {}
        for rel in self.xml(name):
            if rel.tag != f"{{{REL}}}Relationship":
                continue
            ident = rel.get("Id")
            require(bool(ident) and ident not in result, f"Missing/duplicate relationship ID in {name}")
            raw_target = rel.get("Target")
            require(bool(raw_target), f"Missing relationship target in {name}")
            external = rel.get("TargetMode") == "External"
            result[ident] = {
                "type": rel.get("Type", ""), "external": external,
                "target": raw_target if external else self.target(part, raw_target),
            }
        return result

    def targets(self, part: str, kind: str) -> list[str]:
        return [r["target"] for r in self.rels(part).values()
                if not r["external"] and r["type"].endswith("/" + kind)]

    def slides(self) -> list[str]:
        root = self.xml("ppt/presentation.xml")
        relationships = self.rels("ppt/presentation.xml")
        slides = []
        for entry in root.findall("p:sldIdLst/p:sldId", NS):
            ident = entry.get(f"{{{R}}}id")
            require(ident in relationships, "Presentation slide ID has no relationship")
            rel = relationships[ident]
            require(not rel["external"] and rel["type"].endswith("/slide"),
                    "Presentation slide ID does not target a slide")
            slides.append(rel["target"])
        require(bool(slides), "Presentation contains no slides")
        require(len(slides) == len(set(slides)), "Presentation reuses the same slide part")
        return slides


def validate_relationships(package: Package, receipt: Receipt):
    missing = []
    references = 0
    relationship_count = 0
    for name in package.parts:
        if name.endswith(".rels"):
            source = package.source_part(name)
            if source and source not in package.parts:
                missing.append({"part": name, "reason": "relationship source is missing", "target": source})
            for ident, rel in package.rels(source).items():
                relationship_count += 1
                if not rel["external"] and rel["target"] not in package.parts:
                    missing.append({"part": name, "id": ident, "target": rel["target"]})
        elif name.endswith(".xml"):
            rels = package.rels(name)
            for element in package.xml(name).iter():
                for attribute, ident in element.attrib.items():
                    if attribute.startswith("{" + R + "}"):
                        references += 1
                        if ident not in rels:
                            missing.append({"part": name, "id": ident, "reason": "unresolved relationship attribute"})
    receipt.check("all_internal_relationships_resolve", not missing,
                  relationshipCount=relationship_count, relationshipAttributeCount=references, missing=missing)


def image_size(data: bytes) -> tuple[int, int]:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    if data.startswith(b"BM") and len(data) >= 26:
        width, height = struct.unpack("<ii", data[18:26])
        return abs(width), abs(height)
    if data.startswith(b"\xff\xd8"):
        offset = 2
        while offset < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                break
            marker = data[offset]
            offset += 1
            if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                break
            length = struct.unpack(">H", data[offset:offset + 2])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                require(length >= 7 and offset + 7 <= len(data), "Truncated JPEG frame")
                height, width = struct.unpack(">HH", data[offset + 3:offset + 7])
                return width, height
            require(length >= 2, "Invalid JPEG marker length")
            offset += length
    raise ValidationError("Cannot read image dimensions; supported formats: PNG, JPEG, GIF, BMP")


def picture_geometry(pic: ET.Element, parents: dict) -> dict:
    transform = pic.find("p:spPr/a:xfrm", NS)
    require(transform is not None, "Figure lacks an explicit picture transform")
    extent = transform.find("a:ext", NS)
    require(extent is not None, "Figure lacks explicit picture dimensions")
    width, height = float(extent.get("cx", 0)), float(extent.get("cy", 0))
    require(width > 0 and height > 0, "Figure has zero or negative dimensions")
    scale_x = scale_y = 1.0
    parent = parents.get(pic)
    while parent is not None:
        if parent.tag == f"{{{P}}}grpSp":
            group = parent.find("p:grpSpPr/a:xfrm", NS)
            require(group is not None, "Figure group lacks a transform")
            outer, inner = group.find("a:ext", NS), group.find("a:chExt", NS)
            require(outer is not None and inner is not None, "Figure group lacks dimensions")
            child_width, child_height = float(inner.get("cx", 0)), float(inner.get("cy", 0))
            require(child_width > 0 and child_height > 0, "Figure group has invalid child dimensions")
            scale_x *= float(outer.get("cx", 0)) / child_width
            scale_y *= float(outer.get("cy", 0)) / child_height
        parent = parents.get(parent)
    crop = pic.find("p:blipFill/a:srcRect", NS)
    fill_rect = pic.find("p:blipFill/a:stretch/a:fillRect", NS)
    crop_values = [float(node.get(edge, 0)) for node in (crop, fill_rect) if node is not None
                   for edge in ("l", "t", "r", "b")]
    return {
        "widthEmu": width * scale_x, "heightEmu": height * scale_y,
        "uncropped": all(value == 0 for value in crop_values),
        "tiled": pic.find("p:blipFill/a:tile", NS) is not None,
    }


def validate_inputs(spec: dict, profile: dict, manifest: dict):
    require(spec.get("schemaVersion") == 1, "Unsupported or missing spec.schemaVersion (expected 1)")
    slides = spec.get("slides")
    require(isinstance(slides, list) and bool(slides), "spec.slides must be a nonempty list")
    require(number(spec.get("durationSeconds")) and spec["durationSeconds"] > 0,
            "spec.durationSeconds must be a positive finite number")
    require(isinstance(profile.get("roles"), dict), "profile.roles must be an object")
    require(isinstance(profile.get("sourceMedia"), list) and
            all(isinstance(v, str) and v.startswith("ppt/media/") for v in profile["sourceMedia"]),
            "profile.sourceMedia must list template ppt/media parts")
    size = profile.get("slideSize")
    require(isinstance(size, list) and len(size) == 2 and all(number(v) and v > 0 for v in size),
            "profile.slideSize must contain positive width and height in pixels")
    for index, slide in enumerate(slides, 1):
        require(isinstance(slide, dict), f"Slide {index}: expected an object")
        require(isinstance(slide.get("title"), str), f"Slide {index}: missing string title")
        require(slide.get("role") in profile["roles"], f"Slide {index}: undeclared template role")
        require(number(slide.get("seconds")) and slide["seconds"] > 0,
                f"Slide {index}: seconds must be a positive finite number")
        for key in ("cues", "sources"):
            require(isinstance(slide.get(key), list) and all(isinstance(v, str) for v in slide[key]),
                    f"Slide {index}: {key} must be a list of strings")
        require(bool(slide["cues"]) and all(v and "\n" not in v and "\r" not in v for v in slide["cues"]),
                f"Slide {index}: cues must be nonempty single-line strings")
        require(all(v and "\n" not in v and "\r" not in v for v in slide["sources"]),
                f"Slide {index}: sources must be nonempty single-line strings")
        require(isinstance(slide.get("fields", {}), dict) and
                all(isinstance(v, str) for v in slide.get("fields", {}).values()),
                f"Slide {index}: fields must map names to text strings")
        require(isinstance(slide.get("blocks", []), list), f"Slide {index}: blocks must be a list")
        for block in slide.get("blocks", []):
            require(isinstance(block, dict), f"Slide {index}: block must be an object")
            kind = block.get("type")
            require(kind in ("text", "table", "figure"), f"Slide {index}: unsupported block type {kind!r}")
            if kind == "text":
                require(isinstance(block.get("text"), str), f"Slide {index}: text block needs text")
            elif kind == "figure":
                require(isinstance(block.get("path"), str) and bool(block["path"]),
                        f"Slide {index}: figure block needs path")
            else:
                rows = block.get("values")
                require(isinstance(rows, list) and bool(rows) and all(isinstance(row, list) and bool(row) for row in rows),
                        f"Slide {index}: table values must be a nonempty row matrix")
                require(len({len(row) for row in rows}) == 1 and all(isinstance(v, str) for row in rows for v in row),
                        f"Slide {index}: table must be rectangular with string cells")
    require(isinstance(manifest.get("figures"), list), "manifest.figures must be a list")
    require(isinstance(manifest.get("tableSlides"), list), "manifest.tableSlides must be a list")
    for figure in manifest["figures"]:
        require(isinstance(figure, dict), "Manifest figure must be an object")
        slide_num = figure.get("slide")
        require(isinstance(slide_num, int) and not isinstance(slide_num, bool) and 1 <= slide_num <= len(slides),
                "Manifest figure slide must be a valid one-based slide number")
        require(isinstance(figure.get("source"), str) and bool(figure["source"]), "Manifest figure needs source path")
        pixels = figure.get("pixelSize")
        require(isinstance(pixels, list) and len(pixels) == 2 and all(number(v) and v > 0 for v in pixels),
                "Manifest figure needs positive pixelSize [width, height]")
    require(all(isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(slides)
                for n in manifest["tableSlides"]), "manifest.tableSlides contains an invalid slide number")


def validate(candidate: Path, spec_path: Path, profile_path: Path, manifest_path: Path, receipt: Receipt):
    spec, profile, manifest = (read_json(path) for path in (spec_path, profile_path, manifest_path))
    validate_inputs(spec, profile, manifest)
    receipt.check("input_schema", True, specSchemaVersion=1)
    template_path = resolve_input(profile_path, profile["template"])
    require(candidate.is_file(), f"Candidate file is missing: {candidate}")
    require(template_path.is_file(), f"Template file is missing: {template_path}")
    package, template = Package(candidate), Package(template_path)
    slides, template_slides = package.slides(), template.slides()
    receipt.check("candidate_readable", True, path=str(candidate))
    receipt.check("slide_count", len(slides) == len(spec["slides"]), expected=len(spec["slides"]), actual=len(slides))
    total_seconds = sum(slide["seconds"] for slide in spec["slides"])
    receipt.check("planned_duration", math.isclose(total_seconds, spec["durationSeconds"], abs_tol=1e-9, rel_tol=0),
                  expectedSeconds=spec["durationSeconds"], actualSeconds=total_seconds,
                  slideSeconds=[slide["seconds"] for slide in spec["slides"]])
    size = package.xml("ppt/presentation.xml").find("p:sldSz", NS)
    actual_size = [int(size.get("cx", 0)), int(size.get("cy", 0))] if size is not None else None
    emu_per_pixel = profile.get("emuPerPixel", 9525)
    require(number(emu_per_pixel) and emu_per_pixel > 0, "profile.emuPerPixel must be positive")
    expected_size = [round(v * emu_per_pixel) for v in profile["slideSize"]]
    receipt.check("slide_size", actual_size == expected_size, expectedEmu=expected_size, actualEmu=actual_size)
    validate_relationships(package, receipt)
    chart_parts = [part for part in package.parts if part.startswith("ppt/charts/") and part.endswith(".xml")]
    chart_elements = [part for part in slides if any(node.tag.rsplit("}", 1)[-1] in ("chart", "chartEx")
                                                  for node in package.xml(part).iter())]
    receipt.check("no_native_charts", not chart_parts and not chart_elements,
                  chartParts=chart_parts, slidesWithChartElements=chart_elements)
    media = {name: content for name, content in package.parts.items() if name.startswith("ppt/media/")}
    for required_media in profile["sourceMedia"]:
        exists = required_media in template.parts
        matches = [name for name, content in media.items() if exists and content == template.parts[required_media]]
        receipt.check("template_media_byte_identity", bool(matches), sourcePart=required_media,
                      sourceExists=exists, candidateParts=matches)

    expected_table_slides = [i for i, slide in enumerate(spec["slides"], 1)
                             if any(block["type"] == "table" for block in slide.get("blocks", []))]
    actual_table_slides = [i for i, part in enumerate(slides, 1) if native_tables(package.xml(part))]
    receipt.check("table_slide_manifest", manifest["tableSlides"] == expected_table_slides == actual_table_slides,
                  expected=expected_table_slides, manifest=manifest["tableSlides"], actual=actual_table_slides)
    masters = set(package.targets("ppt/presentation.xml", "slideMaster"))

    for index, (part, slide) in enumerate(zip(slides, spec["slides"]), 1):
        root = package.xml(part)
        role = profile["roles"][slide["role"]]
        source_slide = role.get("sourceSlide") if isinstance(role, dict) else None
        receipt.check("template_role_source_exists", isinstance(source_slide, int) and not isinstance(source_slide, bool)
                      and 1 <= source_slide <= len(template_slides), slide=index, role=slide["role"],
                      sourceSlide=source_slide, templateSlideCount=len(template_slides))
        layouts = package.targets(part, "slideLayout")
        layout_masters = package.targets(layouts[0], "slideMaster") if len(layouts) == 1 and layouts[0] in package.parts else []
        valid_links = len(layouts) == 1 and len(layout_masters) == 1 and layout_masters[0] in masters
        receipt.check("slide_layout_and_master", valid_links, slide=index, layouts=layouts, masters=layout_masters)

        text = text_shapes(root)
        expected_text = [slide["title"], *slide.get("fields", {}).values(),
                         *(block["text"] for block in slide.get("blocks", []) if block["type"] == "text")]
        missing_text = [value for value in dict.fromkeys(expected_text)
                        if normalized_text(value) not in text]
        receipt.check("display_text", not missing_text, slide=index,
                      expectedTextCount=len(set(expected_text)), missing=missing_text)
        expected_tables = [[[normalized_text(value) for value in row] for row in block["values"]]
                           for block in slide.get("blocks", []) if block["type"] == "table"]
        actual_tables = native_tables(root)
        # OOXML table order follows z-order, which the builder preserves from spec.
        receipt.check("native_table_values", actual_tables == expected_tables, slide=index,
                      expected=expected_tables, actual=actual_tables)

        note_parts = package.targets(part, "notesSlide")
        expected_notes = ["- " + cue for cue in slide["cues"]] + ["", SOURCE_HEADER] + slide["sources"]
        actual_notes = []
        if len(note_parts) == 1 and note_parts[0] in package.parts:
            note_root = package.xml(note_parts[0])
            bodies = []
            for shape in note_root.findall(".//p:sp", NS):
                ph = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
                body = shape.find("p:txBody", NS)
                if body is not None and (ph is None or ph.get("type") == "body"):
                    bodies.append(body_text(body))
            actual_notes = "\n".join(bodies).split("\n")
            # A terminal empty OOXML paragraph is an editor serialization detail.
            while actual_notes and actual_notes[-1] == "":
                actual_notes.pop()
        receipt.check("speaker_notes_exact", len(note_parts) == 1 and actual_notes == expected_notes,
                      slide=index, expected=expected_notes, actual=actual_notes, notesParts=note_parts)

        spec_figures = [resolve_input(spec_path, block["path"])
                        for block in slide.get("blocks", []) if block["type"] == "figure"]
        figures = [figure for figure in manifest["figures"] if figure["slide"] == index]
        manifest_sources = [resolve_input(manifest_path, figure["source"]) for figure in figures]
        receipt.check("figure_manifest_matches_spec", sorted(map(str, spec_figures)) == sorted(map(str, manifest_sources)),
                      slide=index, expected=list(map(str, spec_figures)), actual=list(map(str, manifest_sources)))
        parents = {child: parent for parent in root.iter() for child in parent}
        pictures = list(root.findall(".//p:pic", NS))
        relationships = package.rels(part)
        used_pictures = set()
        for figure_index, (figure, source) in enumerate(zip(figures, manifest_sources), 1):
            if not receipt.check("figure_source_exists", source.is_file(), slide=index, source=str(source)):
                continue
            source_bytes = source.read_bytes()
            pixels = image_size(source_bytes)
            receipt.check("figure_source_pixel_size", list(pixels) == figure["pixelSize"], slide=index,
                          source=str(source), expected=figure["pixelSize"], actual=list(pixels))
            matches = []
            for picture_index, pic in enumerate(pictures):
                if picture_index in used_pictures:
                    continue
                blip = pic.find("p:blipFill/a:blip", NS)
                ident = blip.get(f"{{{R}}}embed") if blip is not None else None
                rel = relationships.get(ident, {})
                if not rel.get("external", True) and package.parts.get(rel.get("target")) == source_bytes:
                    matches.append((picture_index, pic, rel["target"]))
            receipt.check("slide_figure_byte_identity", bool(matches), slide=index, source=str(source),
                          figure=figure_index, matchingParts=[match[2] for match in matches])
            if not matches:
                continue
            picture_index, pic, media_part = matches[0]
            used_pictures.add(picture_index)
            geometry = picture_geometry(pic, parents)
            ratio = geometry["widthEmu"] / geometry["heightEmu"]
            expected_ratio = pixels[0] / pixels[1]
            receipt.check("figure_uncropped", geometry["uncropped"] and not geometry["tiled"], slide=index,
                          source=str(source), mediaPart=media_part, **geometry)
            # Allow up to two EMUs of extent rounding, plus floating-point error.
            tolerance = max(2 / geometry["heightEmu"], expected_ratio * 1e-6)
            receipt.check("figure_aspect_ratio", abs(ratio - expected_ratio) <= tolerance, slide=index,
                          source=str(source), expected=expected_ratio, actual=ratio, tolerance=tolerance)


def protected_paths(args) -> set[Path]:
    paths = {getattr(args, key).resolve() for key in ("candidate", "spec", "profile", "manifest")}
    # Protect figure/template inputs even on a failed run; never replace one with a receipt.
    for path, key in ((args.profile, "template"),):
        try:
            paths.add(resolve_input(path, read_json(path)[key]))
        except (OSError, ValueError, KeyError):
            pass
    try:
        for slide in read_json(args.spec).get("slides", []):
            for block in slide.get("blocks", []):
                if block.get("type") == "figure":
                    paths.add(resolve_input(args.spec, block["path"]))
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        pass
    try:
        for figure in read_json(args.manifest).get("figures", []):
            paths.add(resolve_input(args.manifest, figure["source"]))
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        pass
    return paths


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("candidate", "spec", "profile", "manifest", "report"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args(argv)
    report_path = args.report.expanduser().resolve()
    if report_path in protected_paths(args):
        print(f"Refusing to overwrite an input with the report: {report_path}", file=sys.stderr)
        return 2
    inputs = {key: str(getattr(args, key).expanduser().resolve())
              for key in ("candidate", "spec", "profile", "manifest")}
    receipt = Receipt(inputs)
    try:
        validate(*(Path(inputs[key]) for key in ("candidate", "spec", "profile", "manifest")), receipt)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ET.ParseError, zipfile.BadZipFile) as exc:
        receipt.check("validation_completed", False, error=f"{type(exc).__name__}: {exc}")
    passed = receipt.finish()
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(receipt.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Cannot write verification receipt: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": receipt.data["status"], "report": str(report_path),
                      "passedChecks": receipt.data["passedChecks"], "failedChecks": receipt.data["failedChecks"]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
