# Template-driven presentation rebuilds

Use this branch when a PPTX template is supplied or already configured. The
[builder](../scripts/build_template_presentation.mjs) imports the retained native
PPTX, duplicates selected source slides, fills mapped text fields, inserts native
text/tables and whole final PNG figures, writes cues, validates and renders the
result. It never invokes an analysis or plotting module.

## Establish the reusable inputs

Read the project's presentation README and existing rebuild entry before writing
new code. Keep approved narrative decisions when the change is only to the template.

On first adoption, inspect the native template and render its relevant sample
pages. Record its source-slide roles, exact shape selectors, reserved content area,
resolved fonts/colors and any demonstrated import compatibility correction in a
project-owned template profile. Preserve the original PPTX and native master/layout
assets. Compare against the actual source appearance, including an embedded preview
or native application rendering when needed to resolve an import discrepancy.
Keep template-specific mappings and local runtime paths outside this skill bundle.

The project keeps four inputs:

- The original `.pptx` and a profile JSON describing how to populate it.
- Ordered content JSON with titles, editable text/table blocks, final-image paths,
  speaking cues, source references and planned time. Position blocks to serve the
  approved account; the schema does not prescribe a narrative per slide.
- Existing finalized PNGs. Figure blocks declare a containing frame; the builder
  fits the whole image proportionally and verifies the embedded bytes.
- A local runtime JSON locating the existing Node packages, Python, presentation
  validators and required font files. Preserve the selected runtime rather than
  installing replacements during a rebuild.

## Input contract

All JSON files use `schemaVersion: 1` where shown. Paths are relative to the JSON
that contains them; runtime paths may be absolute.

The **profile** has `template`, `slideSize: [width, height]` in CSS pixels,
`sourceMedia` (native ZIP member names whose bytes must survive), `requiredFonts`,
optional `contentBottom`, and `roles`. A role has a one-based `sourceSlide`, `fields`
and optional `remove` selectors. Each field maps a content key to
`{selector: {name, text?}, frame?: [x,y,w,h], style?: {...}}`. Selectors must match
exactly one native shape. `title` reads the slide's title; other keys read its
`fields`. Removal selectors clear sample content only. `textStyles` supplies named
font/size/color settings. `tableStyle` supplies typeface, fontSize, headerFill,
headerText, two bodyFills, bodyText, borderColor and borderWidth from the template.

The **content** has `schemaVersion`, `durationSeconds` and ordered `slides`. Each
slide has `role`, `title`, optional `fields`, `seconds`, `cues`, `sources` and `blocks`.
Blocks declare `type` and `frame: [x,y,w,h]`: `text` adds `text` and a named `style`;
`table` adds a rectangular string `values` array and `columnWidths`, with optional
`fontSize`/`totalRow`; `figure` adds a final PNG `path` and `alt`. Counts and captions
come from the analysis evidence; the presentation builder only renders them.

The **runtime** has `nodeModules`, `python`, `presentationTools` and optional
`fontFiles` and `artifactToolVersion`. Pin the tested Artifact Tool version for
repeatable builds; a mismatch stops assembly. On Codex, obtain runtime locations
from the dependency loader and available local fonts. `presentationTools` contains the package-integrity and layout-geometry
validators supplied by the presentation tooling. In another environment, configure
compatible validators before using this builder. The runtime dependency is explicit;
this implementation is not a platform-independent PPTX engine.

## Build and verify

Expose one project rebuild command that calls the canonical builder, with the
chosen runtime's Node executable:

```sh
node /path/to/xenium-reporting/scripts/build_template_presentation.mjs \
  --spec /project/presentations/content.json \
  --profile /project/reference/template-profile.json \
  --runtime /project/presentations/runtime.local.json \
  --output /project/presentations/new-output.pptx \
  --build-dir /project/presentations/.build/new-output
```

Use a new output path. Existing final outputs are protected. The build directory
retains input snapshots, a figure/template manifest, notes, rendered pages and a
verification receipt. The original template stays unchanged. Checksum calculations
are outside this path. Notes, values, native relationships and image comparisons
are checked by the [content verifier](../scripts/verify_template_presentation.py),
followed by package/layout checks and re-import rendering.

For a new template or relevant builder change, inspect the affected rendered pages
against the reference and run a second build from the same inputs to establish
rebuild behavior. Exercise a relevant failure such as a missing figure or ambiguous
placeholder. Reproducibility means the same content, styling and assets; generated
ZIP metadata and object IDs need not be byte-identical. On routine unchanged runs,
reuse these established checks instead of replanning or manually editing the deck.

Deliver the requested PPTX after the checks. Changes to this workflow do not replace
the presentation deliverable. Installation or registration as a personal template
is a separate action and is not needed to rebuild a project deck.
