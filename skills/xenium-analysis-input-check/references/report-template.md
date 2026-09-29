# Report format

Adapt this Markdown outline; the YAML header is a small locator, not a schema.
Keep evidence near each finding. Use prose or tables according to the package's
complexity; additional summary files are unnecessary. Link commands, runtime records
and diagnostic logs as reproduction evidence rather than narrating setup history.

```markdown
---
title: "<package name> — Xenium analysis input check"
type: data-check
package: "<host and supplied path>"
---

## Summary
Lead with what the supplied package supports and which uses remain limited, with
the reason for each consequential limit. Include enough package identity and scale
to make the conclusion unambiguous.

## Package contents
Supplied objects, custom format/field meanings, package/version evidence and existing
processing. State how delivered-file correspondence was established; record content
verification separately from path/size comparisons.

## Findings
For each essential check: observation, file/field evidence, inspection scope
(metadata-only, sampled or full), and any consequence. Distinguish sender evidence from checks run
now; state whether that evidence matches the exact files and cohort. Group related
findings for readability. Identify the representation, cell/specimen scope and join
keys behind each conclusion. Preserve valid subset findings separately from failures.

## Standard items (only when a package standard was supplied)
One row per standard item: item ID, status (met / not met / not confirmed), evidence
or reason, and owner. Name the standard file and whether it is agreed or draft.

## Not checked / unresolved
Relevant unknowns or checks not performed, why, and what they affect. For each
actionable gap, give the next action, responsible party if known (otherwise say
ownership is unresolved), and the evidence needed to close it. Consolidate related
sender requests; separate observed defects from unavailable evidence.
Absent upstream outputs need mentioning only when they limit a relevant conclusion.
Link a data-intake report when source/recipient reconciliation was also requested;
file receipt does not establish object validity or biological quality.
```
