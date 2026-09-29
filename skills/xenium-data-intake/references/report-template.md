# Data intake report

Use one Markdown report. The YAML header is a locator, not a separate tracking system.
Adapt the sections to the delivery, keeping evidence close to conclusions. Save it
outside the inputs and follow the project's filenames and correspondence placement.

```markdown
---
title: "<delivery> — Xenium data intake"
type: data-intake
received: "<host/location>"
baseline: "<source/manifest, or unknown>"
---

## Summary
What was received, the comparison result within its stated scope, and the most
consequential unresolved input. Distinguish agreement with a baseline from fulfillment
of the delivery agreement. Say whether content verification was performed.

## Scope and evidence
State the agreed files/representations/specimens and intentional exclusions, or the
unresolved agreement. Identify the baseline, its origin and its claimed coverage.
Keep format-based expectations and conflicting statements distinguishable.

| Location or evidence | Relative root/scope | Observed interval | Coverage and errors | Content availability |
|---|---|---|---|---|
| <recipient/source/manifest/web subset> | <root and exclusions> | <interval or unknown> | <complete/partial/failed; skips/errors> | <evidence or unknown> |

Link inventories and differences. Report regular-file counts and byte totals within
their actual scope; distinguish directories and symlinks. An archive inventory covers
the archive file unless its contents were separately inspected.

## Findings
For each consequential difference, give the exact relative path or contained-object
requirement, expectation source, observation, coverage and practical consequence.
Separate confirmed missing paths, one-sided observations, type conflicts and size
differences. “Outside this baseline” is not automatically “unwanted.”

Identify candidate alternatives without asserting usability until supported by
analysis-input evidence. Link that evidence with its inspection depth. An urgent
shortlist is not the complete missing-file inventory.

## Unresolved and next actions
List unverified source completeness, unreadable/partial areas, unknown local content
availability, unverified byte identity and unconfirmed object coverage when relevant.
For actionable gaps, name the needed evidence and owner if known. Consolidate a
requested sender follow-up; distinguish a draft from a sent message.
```
