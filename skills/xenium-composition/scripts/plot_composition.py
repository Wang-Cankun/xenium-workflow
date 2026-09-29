#!/usr/bin/env python3
"""Render descriptive composition figures from validated composition summary tables.

This script reads no H5AD and performs no biological group tests. A source
record is defined by --unit-key; its cells are pooled across observations.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "xenium-figures-mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_rgba
from matplotlib import font_manager
from matplotlib.patches import Patch
from matplotlib.text import Text
import numpy as np
import pandas as pd


DEFAULT_THEME = Path(__file__).resolve().parents[2] / "xenium-figures/assets/style.json"
DEFAULT_STYLE = json.loads(DEFAULT_THEME.read_text())
DEFAULT_STYLE.setdefault("group_order", [])
META_KEYS = ["sample_id", "unit_id", "unit_label", "group_label"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_counts(path):
    d = pd.read_csv(path, sep="\t", keep_default_na=False,
                    dtype={"sample_id": str, "cell_type": str})
    keys = ["sample_id", "cell_type", "count", "denominator", "proportion"]
    require(set(keys).issubset(d), f"{path}: missing required count columns")
    require(len(d) > 0, f"{path}: empty count table")
    for key in ["sample_id", "cell_type"]:
        require(d[key].map(lambda x: isinstance(x, str) and bool(x.strip())).all(),
                f"{path}: blank {key}")
    require(not d.duplicated(["sample_id", "cell_type"]).any(), f"{path}: duplicate count rows")
    for key in ["count", "denominator"]:
        d[key] = pd.to_numeric(d[key], errors="raise")
        v = d[key].to_numpy()
        require(np.isfinite(v).all() and (v >= 0).all() and (v == np.floor(v)).all(),
                f"{path}: {key} must be finite nonnegative integers")
        d[key] = d[key].astype("int64")
    d["proportion"] = pd.to_numeric(d["proportion"].replace("", np.nan), errors="raise")
    require(len(d) == d.sample_id.nunique() * d.cell_type.nunique(),
            f"{path}: sample-by-type grid is incomplete")
    sums = d.groupby("sample_id")["count"].sum()
    expected_denominator = d.sample_id.map(sums).to_numpy()
    require(np.array_equal(d.denominator.to_numpy(), expected_denominator),
            f"{path}: denominator differs from retained cell total")
    expected = np.divide(d["count"], d.denominator,
                         out=np.full(len(d), np.nan), where=d.denominator.to_numpy() != 0)
    require(np.allclose(d.proportion, expected, rtol=0, atol=1e-10, equal_nan=True),
            f"{path}: proportion differs from count / denominator")
    return d[keys].copy()


def read_metadata(path, counts, unit_key, group_key, unit_name_key=None):
    d = pd.read_csv(path, sep="\t", keep_default_na=False, dtype=str)
    source_keys = ["sample_id", unit_key, group_key] + ([unit_name_key] if unit_name_key else [])
    require(set(source_keys).issubset(d), f"{path}: missing required metadata columns")
    require(not d.sample_id.duplicated().any(), f"{path}: duplicate sample IDs")
    for key in source_keys:
        require(d[key].str.strip().ne("").all(), f"{path}: blank {key}")
    require(set(d.sample_id) == set(counts.sample_id), f"{path}: metadata/count sample IDs differ")
    for key in [group_key] + ([unit_name_key] if unit_name_key else []):
        require(d.groupby(unit_key)[key].nunique().eq(1).all(),
                f"{path}: inconsistent {key} within {unit_key}")
    expected = d.sample_id.map(counts.groupby("sample_id")["count"].sum())
    for key in ["input_cells", "included_cells", "excluded_cells"]:
        if key in d:
            values = pd.to_numeric(d[key], errors="raise")
            require(np.isfinite(values).all() and values.ge(0).all() and
                    values.eq(np.floor(values)).all(),
                    f"{path}: {key} must be finite nonnegative integers")
            d[key] = values.astype("int64")
    if "included_cells" in d:
        require(np.array_equal(d.included_cells, expected), f"{path}: included_cells differs from counts")
    d["included_cells"] = expected
    if "input_cells" in d:
        require(d.input_cells.ge(d.included_cells).all(), f"{path}: input_cells is below included_cells")
        excluded = d.input_cells - d.included_cells
        if "excluded_cells" in d:
            require(d.excluded_cells.eq(excluded).all(), f"{path}: input_cells != included_cells + excluded_cells")
        d["excluded_cells"] = excluded
    elif "excluded_cells" in d:
        d["input_cells"] = d.included_cells + d.excluded_cells
    return d


def cohort_summary(metadata, retained_cells):
    known = {"input_cells", "excluded_cells"}.issubset(metadata)
    excluded = int(metadata.excluded_cells.sum()) if known else None
    caption = ("Upstream exclusions not recorded" if not known else
               "All supplied cells retained" if excluded == 0 else
               f"{retained_cells:,} retained; {excluded:,} excluded")
    return {"input_cells": int(metadata.input_cells.sum()) if known else None,
            "retained_cells": retained_cells, "excluded_cells": excluded,
            "exclusions_recorded": known, "caption": caption}


def load_style(path):
    style = dict(DEFAULT_STYLE)
    if path:
        supplied = json.loads(Path(path).read_text())
        require(isinstance(supplied, dict), "Theme must be a JSON object")
        for key, value in supplied.items():
            style[key] = ({**style[key], **value} if key in ("palette", "type_labels") else value)
    require(float(style["minimum_font_size"]) >= 7, "minimum_font_size must be at least 7 pt")
    require(float(style["font_size"]) >= float(style["minimum_font_size"]) + 1, "font_size must be at least minimum_font_size + 1")
    require(170 <= float(style["width_mm"]) <= 210, "width_mm must be between 170 and 210")
    require(float(style["dpi"]) >= 300, "dpi must be at least 300")
    require(float(style["axes_linewidth"]) > 0 and float(style["line_width"]) > 0, "Line widths must be positive")
    require(bool(style["formats"]) and len(style["formats"]) == len(set(style["formats"])) and
            set(style["formats"]).issubset({"pdf", "svg", "png"}), "formats must be unique PDF/SVG/PNG extensions")
    for color in list(style["palette"].values()) + [style[k] for k in ["text_color", "secondary_text_color", "grid_color", "background"]]:
        to_rgba(color)
    for key in ["group_order", "type_order"]:
        require(len(style[key]) == len(set(style[key])), f"Duplicate values in {key}")
    return style



def main_style(style, layout):
    """Select final-size main artwork without changing supplementary layouts."""
    selected = dict(style)
    selected["height_mm"] = 7.4 * 25.4
    selected["panel_font_size"] = float(style["font_size"]) + 2
    if layout == "report":
        require("report" in style and "figure" in style["report"],
                "Report layout requires report.figure in the shared style")
        required = {"width_mm", "height_mm", "font_size", "minimum_font_size", "panel_font_size"}
        config = style["report"]["figure"]
        require(required.issubset(config), "report.figure is missing required dimensions or font sizes")
        selected.update({key: float(config[key]) for key in required})
        require(120 <= selected["width_mm"] <= 210 and 120 <= selected["height_mm"] <= 240,
                "Report figure dimensions must be readable page-sized dimensions")
        require(selected["minimum_font_size"] >= 7 and
                selected["font_size"] >= selected["minimum_font_size"] + 1 and
                selected["panel_font_size"] >= selected["font_size"],
                "Report fonts must preserve the minimum size and readable panel labels")
    return selected


def main_caption_metadata(data):
    """Keep explanatory facts outside artwork for the report's editable caption."""
    return {
        "panel_a": "Fractions from counts pooled across observations within each source record",
        "panel_b": "Points are source records; horizontal lines are equally weighted group means of record-level fractions",
        "n_definition": "Number of source records in each supplied group",
        "group_n": {group: int(data["blocks"].group_label.eq(group).sum()) for group in data["groups"]},
        "denominator": "All retained cells across observations in the source record, including Unknown when supplied",
        "zero_denominator": "Displayed as n=0 in panel a and omitted from point and mean calculations in panel b",
        "cohort": data["cohort"]["caption"],
        "unit_limitation": "Source records are defined by unit_key; independent biological replicates are not inferred",
    }



def supplemental_caption_metadata(data, style, limit, page_size):
    """Retain supplementary explanations as editable-caption source facts."""
    row_order = "supplied order" if "detailed_order" in style else "pooled abundance"
    if data["hierarchy"]:
        row_order = "main type, then " + row_order
    captions = {
        "core_inventory": {
            "observations": "Each bar represents one observation; adjacent values are retained cell counts",
            "order": "Observations follow the declared group, source-record and observation order",
            "separators": "Horizontal separators distinguish source records",
            "zero_denominator": "An empty bar marked No retained cells denotes a zero denominator",
            "cohort": data["cohort"]["caption"],
            "pages": math.ceil(data["n_cores"] / page_size),
            "maximum_observations_per_page": page_size,
        }
    }
    if data["detailed_matrix"] is not None:
        captions["detailed_composition"] = {
            "measurement": "Source-record fractions from counts pooled across observations",
            "row_order": row_order,
            "color_scale": f"Retained cells (%), truncated at {limit:g}%; larger values are labelled with actual percentages rounded to the nearest integer",
            "zero_denominator": "Gray denotes a zero-cell denominator, when present",
            "cohort": data["cohort"]["caption"],
            "family_strip": "Row colors identify broad cell families" if data["hierarchy"] else None,
        }
    return captions


def read_hierarchy(path, main, detailed):
    require(detailed is not None, "label-hierarchy requires detailed counts")
    hierarchy = pd.read_csv(path, sep="\t", keep_default_na=False, dtype=str)
    require({"detailed_cell_type", "main_type"}.issubset(hierarchy), "Hierarchy requires detailed_cell_type and main_type columns")
    require(not hierarchy.detailed_cell_type.duplicated().any(), "Hierarchy detailed labels must be unique")
    require(set(hierarchy.detailed_cell_type) == set(detailed.cell_type), "Hierarchy must cover exactly the detailed labels")
    require(set(hierarchy.main_type).issubset(set(main.cell_type)), "Hierarchy references an unknown main type")
    mapping = dict(zip(hierarchy.detailed_cell_type, hierarchy.main_type))
    mapped = detailed.assign(main_type=detailed.cell_type.map(mapping)).groupby(["sample_id", "main_type"])["count"].sum()
    expected = main.set_index(["sample_id", "cell_type"])["count"]
    require(np.array_equal(mapped.reindex(expected.index, fill_value=0).to_numpy(), expected.to_numpy()),
            "Detailed-to-main hierarchy does not reconcile to main counts for every observation")
    return mapping


def prepare(main, detailed, metadata, style, hierarchy=None):
    core_n = main.groupby("sample_id")["count"].sum().sort_index()
    if detailed is not None:
        detailed_n = detailed.groupby("sample_id")["count"].sum().sort_index()
        require(core_n.equals(detailed_n), "Annotation levels disagree on per-core counts")
    style["type_order"] = [t for t in style["type_order"] if t in set(main.cell_type)] + sorted(set(main.cell_type) - set(style["type_order"]))
    require(1 <= len(style["type_order"]) <= 5,
            "Main overview supports one to five broad cell types; use detailed counts for finer labels")
    require(set(main.cell_type).issubset(style["palette"]), "Missing main-type colors")
    groups = [g for g in style["group_order"] if g in set(metadata.group_label)]
    groups += sorted(set(metadata.group_label) - set(groups))
    md = metadata.copy()
    md["group_order"] = md.group_label.map({g: i for i, g in enumerate(groups)})
    md = md.sort_values(["group_order", "unit_id", "sample_id"]).reset_index(drop=True)
    blocks = md.drop_duplicates("unit_id")[META_KEYS[1:] + ["group_order"]].reset_index(drop=True)
    blocks["block_order"] = np.arange(len(blocks))
    blocks["n_cores"] = blocks.unit_id.map(md.groupby("unit_id").size())
    unit_ids = blocks.unit_id.tolist()
    types = style["type_order"]
    detailed_order = []
    if detailed is not None:
        totals = detailed.groupby("cell_type")["count"].sum().sort_values(ascending=False, kind="stable")
        detailed_order = style.get("detailed_order", totals.index.tolist())
        require(len(detailed_order) == len(set(detailed_order)) and set(detailed_order) == set(detailed.cell_type),
                "detailed_order must contain each detailed type exactly once")
        if hierarchy:
            detailed_order = [t for family in types for t in detailed_order if hierarchy[t] == family]

    def aggregate(d, order):
        core = d.merge(md, on="sample_id", validate="many_to_one")
        core["core_order"] = core.sample_id.map({s: i for i, s in enumerate(md.sample_id)})
        core["type_order"] = core.cell_type.map({t: i for i, t in enumerate(order)})
        core = core.sort_values(["core_order", "type_order"]).reset_index(drop=True)
        block = core.groupby(["unit_id", "cell_type"], sort=False)["count"].sum().reset_index()
        block = block.merge(blocks, on="unit_id", validate="many_to_one")
        block["denominator"] = block.unit_id.map(block.groupby("unit_id")["count"].sum())
        block["proportion"] = block["count"].div(block.denominator.replace(0, np.nan))
        block["type_order"] = block.cell_type.map({t: i for i, t in enumerate(order)})
        block = block.sort_values(["block_order", "type_order"]).reset_index(drop=True)
        matrix = block.pivot(index="unit_id", columns="cell_type", values="proportion").reindex(index=unit_ids, columns=order)
        require(int(block["count"].sum()) == int(d["count"].sum()), "Aggregation lost cells")
        positive = block.groupby("unit_id").denominator.first().gt(0)
        require(np.allclose(matrix.loc[positive.reindex(matrix.index)].sum(axis=1), 1), "Block proportions do not sum to 1")
        return core, block, matrix

    main_core, main_block, main_matrix = aggregate(main, types)
    detailed_core, detailed_block, detailed_matrix = (aggregate(detailed, detailed_order) if detailed is not None else (None, None, None))
    summary = main_block.groupby(["group_label", "cell_type"], sort=False).agg(
        mean_proportion=("proportion", "mean"), n_blocks=("unit_id", "size"),
        n_blocks_with_retained_cells=("proportion", "count")).reset_index()
    # Independent oracle: equal weight for each block, regardless of its cell count.
    for row in summary.itertuples():
        chosen = blocks.loc[blocks.group_label.eq(row.group_label), "unit_id"]
        values = main_matrix.loc[chosen, row.cell_type].to_numpy()
        expected = np.mean(values[np.isfinite(values)]) if np.isfinite(values).any() else np.nan
        require(np.isclose(row.mean_proportion, expected, equal_nan=True), "Group mean is not an unweighted block mean")
    return dict(metadata=md, blocks=blocks, groups=groups, types=types,
                detailed_order=detailed_order, main_core=main_core, main_block=main_block,
                detailed_core=detailed_core, detailed_block=detailed_block,
                main_matrix=main_matrix, detailed_matrix=detailed_matrix, summary=summary,
                total_cells=int(core_n.sum()), n_cores=len(core_n), hierarchy=hierarchy,
                cohort=cohort_summary(md, int(core_n.sum())))


def set_style(style):
    base = float(style["font_size"])
    plt.rcParams.update({
        "font.family": style["font_family"], "font.size": base,
        "axes.labelsize": base, "axes.titlesize": base + 1,
        "xtick.labelsize": base - 1, "ytick.labelsize": base - 1,
        "axes.linewidth": style["axes_linewidth"], "xtick.major.width": style["axes_linewidth"], "ytick.major.width": style["axes_linewidth"],
        "pdf.fonttype": 42, "pdf.use14corefonts": False, "svg.fonttype": "none", "savefig.facecolor": style["background"],
        "figure.facecolor": style["background"], "axes.facecolor": style["background"],
        "text.color": style["text_color"], "axes.labelcolor": style["text_color"],
        "xtick.color": style["text_color"], "ytick.color": style["text_color"],
    })
    required_family = style.get("font_required_family", style["font_family"])
    faces = {}
    for weight in ["normal", "bold"]:
        resolved = font_manager.findfont(font_manager.FontProperties(family=style["font_family"], weight=weight),
                                         fallback_to_default=False)
        actual_family = font_manager.get_font(resolved).family_name
        require(actual_family.casefold() == required_family.casefold(),
                f"Required font {required_family!r}; resolved {actual_family!r}")
        faces[weight] = {"family": actual_family, "path": resolved}
    return {"requested_family": style["font_family"], "required_family": required_family,
            "resolved_family": faces["normal"]["family"], "resolved_font_path": faces["normal"]["path"],
            "resolved_fonts": faces}



def clean_axes(ax, style, grid=False):
    ax.spines[["top", "right"]].set_visible(False)
    ax.tick_params(axis="x", length=0, pad=3)
    if grid:
        ax.yaxis.grid(True, color=style["grid_color"], linewidth=style["axes_linewidth"] * .8)
        ax.set_axisbelow(True)


def main_figure(data, style, title):
    width = float(style["width_mm"]) / 25.4
    fig = plt.figure(figsize=(width, float(style.get("height_mm", 7.4 * 25.4)) / 25.4))
    gs = fig.add_gridspec(2, 6, left=.11, right=.982, bottom=.075, top=.59,
                          hspace=.62, wspace=1.3)
    blocks, types, groups = data["blocks"], data["types"], data["groups"]
    p = data["main_matrix"].to_numpy() * 100
    xs = np.arange(len(blocks), dtype=float) + blocks.group_order.to_numpy() * .75
    ax = fig.add_axes([.11, .76, .872, .20])
    bottom = np.zeros(len(blocks))
    for j, t in enumerate(types):
        vals = np.nan_to_num(p[:, j])
        ax.bar(xs, vals, bottom=bottom, width=.82, color=style["palette"][t], linewidth=0)
        bottom += vals
    ax.set(ylim=(0, 100), ylabel="Retained cells (%)", xticks=xs, xticklabels=blocks.unit_id)
    ax.set_yticks([0, 50, 100])
    ax.tick_params(axis="x", labelrotation=90)
    clean_axes(ax, style)
    fig.text(.024, .966, "a", weight="bold", size=style.get("panel_font_size", style["font_size"] + 2))
    for group in groups:
        select = blocks.group_label.eq(group).to_numpy()
        ax.text(np.mean(xs[select]), 105, f"{group} (n = {select.sum()})", ha="center", size=style["font_size"])
    if np.isnan(p).any():
        for x in xs[np.isnan(p).all(axis=1)]:
            ax.text(x, 4, "n=0", rotation=90, ha="center", size=style["minimum_font_size"])
    handles = [Patch(facecolor=style["palette"][t], label=style["type_labels"].get(t, t)) for t in types]
    fig.legend(handles=handles, frameon=False, ncol=5, loc="center",
               bbox_to_anchor=(.546, .68), fontsize=style["minimum_font_size"], handlelength=1, columnspacing=1.2)
    for j, t in enumerate(types):
        row = j // 3
        row_count = min(3, len(types) - 3 * row)
        start = 3 - row_count + 2 * (j % 3)
        ax = fig.add_subplot(gs[row, start:start + 2])
        ax.set_title(style["type_labels"].get(t, t), loc="left", color=style.get("text_color", "#25282B"), weight="bold", pad=7)
        for k, group in enumerate(groups):
            values = p[blocks.group_label.eq(group).to_numpy(), j]
            values = values[np.isfinite(values)]
            offsets = np.linspace(-.16, .16, len(values)) if len(values) > 1 else np.zeros(len(values))
            ax.scatter(k + offsets, values, s=22, color=style["palette"][t],
                       edgecolors="white", linewidths=.35, zorder=3)
            if len(values):
                ax.plot([k - .25, k + .25], [values.mean()] * 2, color=style["text_color"], linewidth=style["line_width"], zorder=4)
        ax.set(xticks=range(len(groups)), xticklabels=groups, ylim=(-2, 102), yticks=[0, 50, 100])
        ax.tick_params(axis="x", labelrotation=45)
        clean_axes(ax, style, grid=True)
        if j % 3 == 0:
            ax.set_ylabel("Retained cells (%)")
        if j == 0:
            fig.text(.024, .606, "b", weight="bold", size=style.get("panel_font_size", style["font_size"] + 2))
    return fig


def heatmap_figure(data, style, title, limit):
    width = float(style["width_mm"]) / 25.4
    height = max(6.8, 2.2 + .20 * len(data["detailed_order"]))
    fig = plt.figure(figsize=(width, height))
    ax = fig.add_axes([.285, .18, .69, .75])
    matrix = data["detailed_matrix"].to_numpy().T * 100
    cmap = matplotlib.colormaps[style["heatmap_cmap"]].copy()
    cmap.set_bad("#D1D5DB")
    img = ax.imshow(matrix, vmin=0, vmax=limit, cmap=cmap, aspect="auto", interpolation="nearest")
    blocks = data["blocks"]
    ax.set_xticks(np.arange(len(blocks)), blocks.unit_id, rotation=90)
    ax.set_yticks(np.arange(len(data["detailed_order"])), data["detailed_order"])
    ax.tick_params(length=0, pad=4)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for group in data["groups"]:
        indices = np.flatnonzero(blocks.group_label.eq(group).to_numpy())
        ax.text(indices.mean(), 1.02, group, transform=ax.get_xaxis_transform(), ha="center", va="bottom", size=style["font_size"])
        if indices[-1] != len(blocks) - 1:
            ax.axvline(indices[-1] + .5, color="white", linewidth=2)
    if data["hierarchy"]:
        families = [data["hierarchy"][t] for t in data["detailed_order"]]
        strip = fig.add_axes([.278, .18, .005, .75])
        strip.imshow(np.asarray([to_rgba(style["palette"][family]) for family in families])[:, None, :],
                     aspect="auto", interpolation="nearest")
        strip.set_xticks([])
        strip.set_yticks([])
        strip.axis("off")
        for i in range(1, len(families)):
            if families[i] != families[i - 1]:
                ax.axhline(i - .5, color=style["background"], linewidth=1.5)
        handles = [Patch(facecolor=style["palette"][t], label=style["type_labels"].get(t, t)) for t in data["types"]]
        fig.legend(handles=handles, frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(.53, .99),
                   fontsize=style["minimum_font_size"], handlelength=1, columnspacing=1.2)
    for row, col in zip(*np.where(matrix > limit)):
        ax.text(col, row, f"{matrix[row, col]:.0f}", color="white", ha="center", va="center", size=style["minimum_font_size"])
    cax = fig.add_axes([.285, .07, .38, .022])
    cbar = fig.colorbar(img, cax=cax, orientation="horizontal", extend="max" if np.nanmax(matrix) > limit else "neither")
    cbar.set_ticks(np.linspace(0, limit, 5), labels=[f"{v:g}%" for v in np.linspace(0, limit, 5)])
    cbar.outline.set_visible(False)
    cbar.set_label("Retained cells (%)", size=style["font_size"], labelpad=4)
    return fig


def core_figure(data, style, title, page, page_size):
    total_pages = math.ceil(data["n_cores"] / page_size)
    chunks = np.array_split(np.arange(data["n_cores"]), total_pages)
    md = data["metadata"].iloc[chunks[page]]
    matrix = data["main_core"].pivot(index="sample_id", columns="cell_type", values="proportion").reindex(index=md.sample_id, columns=data["types"])
    ns = data["main_core"].groupby("sample_id").denominator.first().reindex(md.sample_id)
    fig = plt.figure(figsize=(float(style["width_mm"]) / 25.4, 8.3))
    ax = fig.add_axes([.18, .135, .68, .805])
    ys = np.arange(len(md))
    left = np.zeros(len(md))
    for t in data["types"]:
        vals = np.nan_to_num(matrix[t].to_numpy()) * 100
        ax.barh(ys, vals, left=left, height=.76, color=style["palette"][t], linewidth=0)
        left += vals
    ax.set(xlim=(0, 100), ylim=(len(chunks[0]) - .4, -.8), yticks=ys, yticklabels=md.sample_id,
           xticks=[0, 25, 50, 75, 100], xlabel="Retained cells (%)")
    ax.tick_params(axis="y", length=0)
    clean_axes(ax, style)
    ax.text(1.025, 1.014, "Cells", transform=ax.transAxes, size=style["font_size"], weight="bold")
    for y, count in zip(ys, ns):
        ax.text(1.025, y, f"{count:,}", transform=ax.get_yaxis_transform(), va="center", size=style["minimum_font_size"])
        if count == 0:
            ax.text(1, y, "No retained cells", size=style["minimum_font_size"], va="center")
    block_values = md.unit_id.tolist()
    for i in range(1, len(block_values)):
        if block_values[i] != block_values[i - 1]:
            ax.axhline(i - .5, color=style["grid_color"], linewidth=style["axes_linewidth"] * .75, zorder=0)
    handles = [Patch(facecolor=style["palette"][t], label=style["type_labels"].get(t, t)) for t in data["types"]]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.52, .035), ncol=5,
               frameon=False, fontsize=style["minimum_font_size"], handlelength=1, columnspacing=1.2)
    return fig


def audit_figure(fig, style=None):
    """Check page bounds and tick-label collisions at the saved physical size."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bounds = fig.bbox
    problems = []
    minimum_font = float((style or DEFAULT_STYLE)["minimum_font_size"])
    texts = [t for t in fig.findobj(Text) if t.get_visible() and t.get_text().strip()]
    for t in texts:
        box = t.get_window_extent(renderer)
        if box.width and box.height and (box.x0 < bounds.x0 - 1 or box.y0 < bounds.y0 - 1 or
                                         box.x1 > bounds.x1 + 1 or box.y1 > bounds.y1 + 1):
            problems.append("Text outside page: " + t.get_text())
        if t.get_fontsize() < minimum_font:
            problems.append(f"Text smaller than {minimum_font:g} pt: " + t.get_text())
    for ax in fig.axes:
        if not ax.axison:
            continue
        for labels in [ax.get_xticklabels(), ax.get_yticklabels()]:
            boxes = [(t.get_text(), t.get_window_extent(renderer)) for t in labels if t.get_visible() and t.get_text()]
            for (first, b1), (second, b2) in zip(boxes, boxes[1:]):
                if b1.overlaps(b2):
                    problems.append(f"Adjacent tick labels overlap: {first} / {second}")
        # Axes labels (including colorbar labels) must not collide with captions.
        for label in [ax.xaxis.label, ax.yaxis.label, ax.title]:
            if label.get_visible() and label.get_text():
                b1 = label.get_window_extent(renderer)
                for caption in fig.texts:
                    if caption.get_visible() and caption.get_text() and b1.overlaps(caption.get_window_extent(renderer)):
                        problems.append(f"Axes text overlaps figure text: {label.get_text()} / {caption.get_text()}")
    require(not problems, "Figure layout audit failed: " + "; ".join(problems))
    return {"text_elements": len(texts), "minimum_font_pt": min(t.get_fontsize() for t in texts),
            "text_within_page": True, "adjacent_tick_labels_do_not_overlap": True,
            "axes_labels_and_figure_captions_do_not_overlap": True,
            "maximum_font_pt": max(t.get_fontsize() for t in texts),
            "font_sizes_pt": sorted({t.get_fontsize() for t in texts}),
            "width_mm": float(fig.get_size_inches()[0] * 25.4),
            "height_mm": float(fig.get_size_inches()[1] * 25.4),
            "width_inches": float(fig.get_size_inches()[0]), "height_inches": float(fig.get_size_inches()[1])}


def save_figure(fig, directory, name, style):
    audit = audit_figure(fig, style)
    files = []
    for ext in style["formats"]:
        path = directory / f"{name}.{ext}"
        fig.savefig(path, dpi=style["dpi"], metadata={"Creator": "plot_composition.py"} if ext != "png" else None)
        files.append(path.name)
    plt.close(fig)
    return {"name": name, "files": files, "png_dpi": style["dpi"] if "png" in style["formats"] else None, "layout_audit": audit}


def run(args):
    style = load_style(args.theme)
    if args.group_order:
        style["group_order"] = [v.strip() for v in args.group_order.split(",")]
        require(all(style["group_order"]) and len(style["group_order"]) == len(set(style["group_order"])),
                "group-order must contain unique, nonempty comma-separated labels")
    require(0 < args.heatmap_max_percent <= 100, "Heatmap maximum must be in (0, 100]")
    require(8 <= args.cores_per_page <= 24, "cores-per-page must be between 8 and 24")
    require(bool(args.detailed_counts) == bool(args.detailed_metadata), "Detailed counts and metadata must be supplied together")
    main = read_counts(args.main_counts)
    main_md = read_metadata(args.main_metadata, main, args.unit_key, args.group_key, args.unit_name_key)
    detailed = None
    if args.detailed_counts:
        detailed = read_counts(args.detailed_counts)
        detailed_md = read_metadata(args.detailed_metadata, detailed, args.unit_key, args.group_key, args.unit_name_key)
        require(set(main_md) == set(detailed_md), "Annotation levels have different metadata columns")
        compare_columns = sorted(main_md.columns)
        require(main_md.sort_values("sample_id")[compare_columns].reset_index(drop=True).equals(
            detailed_md.sort_values("sample_id")[compare_columns].reset_index(drop=True)),
            "Annotation levels disagree on sample metadata")
    metadata = pd.DataFrame({"sample_id": main_md.sample_id, "unit_id": main_md[args.unit_key],
                             "group_label": main_md[args.group_key],
                             "unit_label": main_md[args.unit_name_key or args.unit_key]})
    for key in ["input_cells", "included_cells", "excluded_cells"]:
        if key in main_md:
            metadata[key] = main_md[key]
    hierarchy = read_hierarchy(args.label_hierarchy, main, detailed) if args.label_hierarchy else None
    data = prepare(main, detailed, metadata, style, hierarchy)
    selected_main_style = main_style(style, args.layout)
    font = set_style(selected_main_style)
    output = Path(args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=False)
    figures = [save_figure(main_figure(data, selected_main_style, args.title), output, "01-main-composition", selected_main_style)]
    set_style(style)
    if detailed is not None and not args.main_only:
        figures.append(save_figure(heatmap_figure(data, style, args.title, args.heatmap_max_percent), output, "02-detailed-composition", style))
    for page in range(0 if args.main_only else math.ceil(data["n_cores"] / args.cores_per_page)):
        figures.append(save_figure(core_figure(data, style, args.title, page, args.cores_per_page),
                                   output, f"S1-core-inventory-{page + 1:02d}", style))
    for key in ["main_core", "main_block", "detailed_core", "detailed_block", "summary"]:
        if data[key] is not None:
            data[key].rename(columns={"core_order": "observation_order", "block_order": "unit_order", "n_cores": "n_observations",
                                      "n_blocks": "n_units", "n_blocks_with_retained_cells": "n_units_with_retained_cells"}).to_csv(
                output / f"{key.replace('_core', '_observation').replace('_block', '_unit')}_plotted.tsv", sep="\t", index=False, na_rep="")
    clipped = None
    if detailed is not None:
        clipped = data["detailed_block"].loc[data["detailed_block"].proportion.gt(args.heatmap_max_percent / 100)].copy()
        clipped["displayed_percent_label"] = (clipped.proportion * 100).round().astype(int)
        clipped.to_csv(output / "heatmap_saturated_cells.tsv", sep="\t", index=False)
    manifest = {
        "status": "complete", "title": args.title,
        "inputs": {k: str(Path(getattr(args, k)).resolve()) if getattr(args, k) else None for k in
                   ["main_counts", "main_metadata", "detailed_counts", "detailed_metadata"]},
        "theme_input": str(Path(args.theme).resolve()) if args.theme else None,
        "label_hierarchy_input": str(Path(args.label_hierarchy).resolve()) if args.label_hierarchy else None,
        "label_hierarchy": hierarchy,
        "effective_style": style,
        "main_layout": args.layout,
        "main_only": args.main_only,
        "effective_main_style": selected_main_style,
        "main_caption_metadata": main_caption_metadata(data),
        "supplemental_caption_metadata": ({} if args.main_only else
            supplemental_caption_metadata(data, style, args.heatmap_max_percent, args.cores_per_page)),
        "font": font,
        "versions": {"python": platform.python_version(), "matplotlib": matplotlib.__version__,
                     "pandas": pd.__version__, "numpy": np.__version__},
        "cohort": data["cohort"],
        "totals": {"retained_cells": data["total_cells"], "observations": data["n_cores"], "source_units": len(data["blocks"]),
                   "main_types": len(data["types"]), "detailed_types": len(data["detailed_order"])},
        "units": {"unit_key": args.unit_key, "unit_name_key": args.unit_name_key, "group_key": args.group_key,
                  "source_record": "defined by unit_key; biological identity is not inferred",
                  "unit_proportion": "sum of type counts across unit observations / sum of all retained cells across unit observations",
                  "group_mean": "unweighted arithmetic mean of unit proportions with nonzero denominators",
                  "inference": "descriptive only; no tests or uncertainty intervals"},
        "order": {"groups": data["groups"], "units": data["blocks"].unit_id.tolist(),
                  "observations": data["metadata"].sample_id.tolist(), "detailed_types": data["detailed_order"]},
        "heatmap": {"unit": "percent", "vmin": 0, "vmax": args.heatmap_max_percent,
                    "row_standardization": False, "saturated_cells": len(clipped) if clipped is not None else 0,
                    "saturated_cell_labels": "actual percent rounded to nearest integer"},
        "numerical_checks": ["complete per-observation type grids", "finite integer counts", "per-observation denominator/proportion agreement",
                             "unit metadata consistency", "total cells conserved", "positive-denominator unit fractions sum to one",
                             "group means equally weight units", "supplied exclusion counts reconcile with retained counts"] + (["identical metadata and retained counts across annotation levels"] if detailed is not None else [])
                             + (["detailed-to-main hierarchy is unique, complete and reconciles counts for every observation"] if hierarchy else []),
        "data_files": sorted(path.name for path in output.glob("*.tsv")),
        "figures": figures,
        "visual_review": "not recorded by the script; inspect rendered figures at their stated physical size",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"output_dir": str(output), "totals": manifest["totals"], "figures": len(figures),
                      "saturated_heatmap_cells": len(clipped) if clipped is not None else 0}, indent=2))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ["main-counts", "main-metadata"]:
        p.add_argument("--" + name, required=True, type=Path)
    for name in ["detailed-counts", "detailed-metadata"]:
        p.add_argument("--" + name, type=Path)
    p.add_argument("--unit-key", required=True, help="Metadata column defining pooled source records")
    p.add_argument("--group-key", required=True, help="Metadata column defining descriptive groups")
    p.add_argument("--unit-name-key", help="Optional source record name column; does not define pooling")
    p.add_argument("--label-hierarchy", type=Path, help="Optional detailed_cell_type/main_type TSV; must reconcile to main counts")
    p.add_argument("--group-order", help="Comma-separated group labels; otherwise theme order, then sorted remaining labels")
    p.add_argument("--output-dir", required=True, type=Path, help="Must not already exist")
    p.add_argument("--theme", type=Path, help="JSON overrides for palette, typography and ordering")
    p.add_argument("--title", default="Cell composition", help="Report metadata title; main artwork has no document heading")
    p.add_argument("--layout", choices=["publication", "report"], default="publication",
                   help="Main figure dimensions and fonts; report uses the shared report.figure style")
    p.add_argument("--main-only", action="store_true", help="Export only the main figure and its companion data")
    p.add_argument("--heatmap-max-percent", default=40, type=float)
    p.add_argument("--cores-per-page", default=24, type=int)
    return p


if __name__ == "__main__":
    run(parser().parse_args())
