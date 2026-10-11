<!--
SPEC LINE FORMAT (BUILD_SPEC §9.12). check_spec.py parses this document; keep the section
headings exactly as written below.

Every requirement, business rule, recommendation and acceptance criterion is ONE bullet:

    - **<LINE-ID>** [(draft) ]<statement> <tag> [<tag> ...]

    LINE-ID   FR-nnn | NFR-nnn | BR-nnn | AC-nnn           (unique in the document)
    (draft)   only on AC lines whose primary item is not Approved, Decided or Explicit
    tag       "[" SOURCE ": " ITEM-ID [" · " LABEL] "]"
    SOURCE    Customer | Mockup | Research | Decision | Inferred | Assumption
    ITEM-ID   REQ-… | SCR-… | F-GAP-… | FEA-… | ASM-… | DEC-… | GAP-…
    LABEL     the label status_rules.py derived for that item (status_labels.json), exactly

The FIRST tag carries the primary item's label. Further tags list extra evidence.
State-transition tables use the same tags in their Provenance column.

Placement: rejected items only under "Out of Scope / Rejected"; deferred items only under
"Deferred"; superseded items only in the Decisions Log; dropped and citation-failed findings
only under "Sources > Limitations"; pending findings nowhere.

Assumptions you add are ASM-W-nnn, labelled Assumption, listed in Open Questions and in the
machine-readable block at the end.
-->

# <Feature name>: Feature Specification

## 1. Document Status

- Run ID: <run id>
- Date: <yyyy-mm-dd>
- Run mode: <normal | fixture>
- Publication status: <set in the final pass from run_summary.json>
- Known limitations: <capture, research and review limitations>
- Open stale items: <ids with labels, or none>
- Unresolved blocking issues: <list, or none>

## 2. Executive Summary

<Plain English for non-technical readers: purpose, key features in scope, key open decisions.>

## 3. Goals and Scope

### Goals

### In Scope

### Out of Scope / Rejected

<Each item with its DEC id (Rejected: DEC-xxx), or its REQ id when the customer excluded it.
Never infer exclusions from absence in the mockup.>

### Deferred

<Each item with Deferred: DEC-xxx.>

## 4. Users and Roles

<Known roles, responsibilities and permissions; unknown roles flagged.>

## 5. Existing Mockup Coverage

<Screens, components, observed states, flows, ambiguous behaviours, capture limitations.>

## 6. Requirements Traceability

| REQ | Requirement | Treatment | Label | References |
|---|---|---|---|---|

<Every REQ: addressed | partially addressed | unresolved | out of scope.>

## 7. Gaps Identified

| GAP | Gap | Approval | Path | Priority | Status | Rationale |
|---|---|---|---|---|---|---|

<Status: addressed | open (researched | customer decision pending | resolved by DEC-xxx).>

## 8. Functional Requirements

### <Feature area>

<Purpose; user story where useful.>

#### Confirmed requirements

#### Recommendations awaiting approval

#### Acceptance criteria

## 9. State Transitions and Edge Cases

### <Entity> lifecycle

| State | Event | Next state | Who can trigger | Provenance |
|---|---|---|---|---|

<Mark undecided transitions as Unknown rather than choosing them.>

## 10. Non-Functional Requirements

<NFR bullets, only those justified by input, evidence or labelled analysis. No invented numbers.>

## 11. Data Model and Business Rules

<Entities, fields (visible vs inferred), relationships, constraints, BR bullets. Never claim
knowledge of a schema that was not inspected.>

## 12. Screens and User Flows

## 13. Integrations and Dependencies

## 14. Security, Privacy, and Error Handling

## 15. Decisions Log

| DEC | Checkpoint | Decided | Verbatim answer | Interpretation | Items affected | Supersedes / superseded by |
|---|---|---|---|---|---|---|

## 16. Open Questions and Assumptions

| ID | Text | Why it matters | Related items | Impact | Blocking | Owner | Status |
|---|---|---|---|---|---|---|---|

<Every ASM id used and every stale item appears here.>

## 17. Research Findings and Recommendations

<Kept findings only: what the source establishes, how it applies, recommendation,
limitations, label.>

## 18. Sources

| SRC | Title | URL | Publisher | Published | Fetched | Findings | Limitations |
|---|---|---|---|---|---|---|---|

### Limitations

<Dropped and citation-failed findings with their reasons, only to explain research gaps,
never as evidence.>

```json asm-w
[]
```
