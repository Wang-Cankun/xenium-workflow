# Package standard template

A package standard records what a sender promises when calling a package ready.
It belongs to the project, which fills in the fields, owners and agreement status;
this skill only checks packages against it. Keep project-specific names and paths in
the project copy, not here.

```markdown
# <program> package standard

Status: <draft / agreed with <names> on <source of agreement>>
Scope: <what one package covers, e.g. one H5AD per lab assembled from several TMAs>

| ID | Item | Owner | How the recipient checks it |
|---|---|---|---|
| P1 | Package scope: which specimens/cores are in and which are excluded | | Specimen set against the manifest |
| P2 | Cell counts per specimen, with any QC removal counted | | Per-specimen counts against manifest and QC rule |
| P3 | Expression layers and their meanings (raw counts, normalized) | | Layer semantics, count integrity |
| P4 | Unique cell IDs and a join key back to source objects | | Uniqueness, key present for all cells |
| P5 | Specimen fields (slide/TMA, core, block) for every cell | | Completeness, one slide per core |
| P6 | Spatial coordinates, their key, units and frame | | Presence, finiteness, stated units/frame |
| P7 | Cell annotations with method, reference and version | | Columns present, provenance stated |
| P8 | Specimen table to biological source and group, unknowns named | | Every specimen mapped or explicitly unknown |
| P9 | QC rule and how filtered cells are represented | | Rule stated, flag consistent |
| P10 | README and source manifest | | Present and consistent with the object |
| P11 | Sender check evidence on the exact delivered file | | Refers to the delivered file and cohort |

Items the sender marks not applicable carry a reason. Gaps go to the named owner in
one request; a corrected package is a new sender version.
```

Add, drop or rename items to fit the program; keep each item checkable from the
package, its documentation or supplied evidence.
