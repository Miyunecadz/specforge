# Award Supplier Package: Feature Specification

## 1. Document Status

- Run ID: 20261011-103154-ac03d1
- Date: 2026-10-11
- Run mode: fixture
- Publication status: pending final pass
- Known limitations: The mockup capture is complete (4 pages, fixture mode) but is static HTML, so the behaviour of the Award Package button and of search is not shown, and no loading, error, confirmation or success states were captured. Research ran in fixture mode; every kept finding rests on a fixture page that states it is not real documentation (low confidence, no publication date). No technical documents were supplied, so no integration, schema or sending-system facts are established. Two of the four research findings recorded for the approved gaps were dropped (see Limitations in section 18).
- Open stale items: none
- Unresolved blocking issues: Q-002 (how the supplier is chosen and what happens with no quotes attached) and Q-004 (what the user sees while an award processes, succeeds or fails) are open and recorded as blocking (DEC-011 left them open). REQ-001 and REQ-003 still carry the label Unknown in the status records.

## 2. Executive Summary

This feature lets a package manager award a supplier package to one supplier. The customer has stated that an award is final and cannot be undone by anyone, that an awarded package becomes read-only for everyone with all fields locked, and that the winning supplier is emailed when the award is made. Suppliers who lose are not told by the system.

Also approved: a confirmation step before the award is committed, and a visible failure message to staff if the award email cannot be delivered (the award stays in force either way).

Key open decisions: how the package manager actually picks the supplier (the mockup shows only a note box and an Award Package button), what happens when a package has no quotes attached yet the button is enabled, what the user sees while an award processes and when it succeeds or fails, who is allowed to award, and what the award email says. Several research-based suggestions come from low-confidence test fixture sources and still await approval.

## 3. Goals and Scope

### Goals

- Let package managers award a supplier package to one supplier. [Customer: REQ-001 · Unknown] [Decision: DEC-005]
- Make an awarded package read-only for everyone, with all fields locked. [Customer: REQ-002 · Approved: DEC-005] [Decision: DEC-003]
- Email the winning supplier when the award is made. [Customer: REQ-003 · Unknown] [Decision: DEC-004] [Decision: DEC-009]

### In Scope

- Awarding a package to one supplier chosen from the quotes attached to it. [Customer: FEA-002 · Explicit] [Decision: DEC-001]
- A single, final award per package, protected against repeated or simultaneous attempts. [Customer: FEA-003 · Explicit] [Decision: DEC-002]
- Full lock of awarded packages. [Customer: FEA-004 · Explicit] [Decision: DEC-003]
- Email to the winning supplier at award. [Customer: FEA-005 · Explicit]
- Confirmation step before the award is committed. [Research: FEA-008 · Approved: DEC-008]
- Showing an email delivery failure to staff. [Research: FEA-007 · Approved: DEC-008]
- Gaps approved for research: GAP-004 (outcome of pressing Award Package) and GAP-005 (confirmation before an irreversible award), both Approved: DEC-006.

### Out of Scope / Rejected

All other gaps were rejected by DEC-007 ("Reject every other gap."). Rejecting a gap removes it from this run's tracking and research; it does not decide the underlying behaviour, and the related behaviours that remain undecided are listed in section 8 and section 16. Nothing here is excluded by inference from the mockup.

- GAP-001 Award Package is enabled on a package with no quotes attached (Rejected: DEC-007)
- GAP-002 No way to choose which supplier receives the award (Rejected: DEC-007)
- GAP-003 Who may award, and who may see which packages (Rejected: DEC-007)
- GAP-006 Duplicate and concurrent award attempts (Rejected: DEC-007)
- GAP-007 Notification recipients and content are undefined (Rejected: DEC-007)
- GAP-008 Email delivery failure after an award (Rejected: DEC-007)
- GAP-009 Traceability of who awarded and when (Rejected: DEC-007)
- GAP-010 Award note rules and where the note appears (Rejected: DEC-007)
- GAP-011 How quotes are attached and what they contain (Rejected: DEC-007)
- GAP-012 Package status values and which allow award (Rejected: DEC-007)
- GAP-013 Accessibility of the disabled award button and award status messages (Rejected: DEC-007)
- GAP-014 Retention and deletion of locked awarded packages (Rejected: DEC-007)
- GAP-015 Package list search, sorting and paging behaviour (Rejected: DEC-007)
- GAP-016 Award date, currency and time zone formats (Rejected: DEC-007)
- GAP-017 Reports screen content and link to awards (Rejected: DEC-007)

### Deferred

None. No item is deferred by any recorded decision.

## 4. Users and Roles

- Package manager: may award a supplier package to one supplier. Whether "package manager" is a distinct role in the product is an assumption; no role or signed-in user appears in the capture. [Customer: REQ-001 · Unknown] [Assumption: ASM-G-002 · Assumption]
- Any user: cannot change an awarded package; nobody can undo an award. [Customer: REQ-002 · Approved: DEC-005] [Decision: DEC-003] [Decision: DEC-002]
- Winning supplier: receives an email when the award is made. [Customer: FEA-005 · Explicit] [Decision: DEC-004]
- Unsuccessful bidders: not told by the system. [Customer: REQ-003 · Unknown] [Decision: DEC-009]
- Staff: are shown a failure when the award email cannot be delivered; which staff, and how, is not established. [Research: FEA-007 · Approved: DEC-008]
- Unknown: whether any role other than package managers may award, whether a package manager may award any package or only certain ones, and which packages each user can see are not stated. [Customer: FEA-001 · Explicit]

## 5. Existing Mockup Coverage

Capture status: complete, fixture mode, 4 pages captured, 0 failed. The mockup is static HTML.

- Supplier packages list (PAGE-001): table with Package, Supplier, Value, Status; a Search box; a View details link per row; default state shows PKG-104 Open and PKG-105 Awarded. [Mockup: SCR-001 · Observed]
- Reports (PAGE-002): shows only the text "Coming soon." [Mockup: SCR-002 · Observed]
- PKG-104 Kitchen refit (PAGE-003): supplier, value, status Open; a Quotes section reading "No quotes attached yet."; an Award note textarea (no visible required marker); an enabled Award Package button that has no link or form action. [Mockup: SCR-003 · Observed] [Mockup: SCR-012 · Observed] [Mockup: SCR-028 · Observed]
- PKG-105 Roof repair (PAGE-004): status "Awarded on 2 Oct 2026" and a disabled Award Package button. [Mockup: SCR-004 · Observed] [Mockup: SCR-015 · Observed]
- Package data visible in the mockup: package identifier and title, supplier, value, status (Open, Awarded), award date and award note. The awarding user and quote contents are not shown (inferred only). [Mockup: SCR-029 · Observed] [Mockup: SCR-030 · Observed] [Mockup: SCR-031 · Observed]
- Ambiguous behaviours recorded by the capture: who may award; whether the note is required or length-limited; any confirmation or success/failure display; whether an award can be revoked; whether a package can be awarded with no quotes; which supplier is awarded; why the button is disabled on PKG-105; what search matches; whether the table is sortable or paginated; all possible status values; how quotes are attached; what Reports will contain. [Mockup: SCR-012 · Observed] [Mockup: SCR-015 · Observed]
- Capture limitations: only two package detail pages exist; no loading, error, confirmation or success states are shown for the award action; button and search behaviour are not shown.

## 6. Requirements Traceability

| REQ | Requirement | Treatment | Label | References |
|---|---|---|---|---|
| REQ-001 | Package managers must be able to award a supplier package to one supplier. | partially addressed | Unknown | FR-001, FR-002, FR-003, FR-004, FR-005, FR-006, BR-001, BR-004; DEC-001, DEC-002, DEC-005; open: Q-002 |
| REQ-002 | Awarded packages should be read-only. | addressed | Approved: DEC-005 | FR-009, FR-010, BR-003, AC-006; DEC-003, DEC-005 |
| REQ-003 | Suppliers must be notified when they win. | partially addressed | Unknown | FR-017, FR-018, FR-019, FR-021, AC-010, AC-011; DEC-004, DEC-009, DEC-005; open: email content, address source |

## 7. Gaps Identified

| GAP | Gap | Approval | Path | Priority | Status | Rationale |
|---|---|---|---|---|---|---|
| GAP-001 | Award Package is enabled on a package with no quotes attached | rejected (DEC-007) | customer | critical | rejected (DEC-007); not researched or resolved | Rejected by user; behaviour with no quotes remains undecided (see Q-002) |
| GAP-002 | No way to choose which supplier receives the award | rejected (DEC-007) | customer | critical | rejected (DEC-007); not researched or resolved | Rejected by user; supplier-choice mechanism remains undecided (see Q-002) |
| GAP-003 | Who may award, and who may see which packages | rejected (DEC-007) | customer | critical | rejected (DEC-007); not researched or resolved | Rejected by user; roles and visibility remain unestablished |
| GAP-004 | Outcome of pressing Award Package is not shown | approved (DEC-006) | both | critical | open (researched) | Research covered only email failure after award (F-GAP-004-01); success and failure of the award itself remain undecided (Q-004 open, DEC-011) |
| GAP-005 | No confirmation shown before an irreversible award | approved (DEC-006) | both | critical | addressed | Confirmation step approved via FEA-008 (DEC-008); contents beyond package and supplier are not covered |
| GAP-006 | Duplicate and concurrent award attempts | rejected (DEC-007) | research | critical | rejected (DEC-007); not researched or resolved | Rejected by user; the customer-stated rules of one final award per package still apply (FEA-003) |
| GAP-007 | Notification recipients and content are undefined | rejected (DEC-007) | both | critical | rejected (DEC-007); not researched or resolved | Rejected by user; recipients later answered by DEC-009 (Q-001) |
| GAP-008 | Email delivery failure after an award | rejected (DEC-007) | both | important | rejected (DEC-007); not researched or resolved | Rejected by user; failure display covered separately by FEA-007 (DEC-008) |
| GAP-009 | Traceability of who awarded and when | rejected (DEC-007) | both | important | rejected (DEC-007); not researched or resolved | Rejected by user |
| GAP-010 | Award note rules and where the note appears | rejected (DEC-007) | customer | important | rejected (DEC-007); not researched or resolved | Rejected by user |
| GAP-011 | How quotes are attached and what they contain | rejected (DEC-007) | customer | important | rejected (DEC-007); not researched or resolved | Rejected by user |
| GAP-012 | Package status values and which allow award | rejected (DEC-007) | customer | important | rejected (DEC-007); not researched or resolved | Rejected by user |
| GAP-013 | Accessibility of the disabled award button and award status messages | rejected (DEC-007) | research | important | rejected (DEC-007); not researched or resolved | Rejected by user |
| GAP-014 | Retention and deletion of locked awarded packages | rejected (DEC-007) | customer | optional | rejected (DEC-007); not researched or resolved | Rejected by user; DEC-010 separately records a seven-year retention of award records |
| GAP-015 | Package list search, sorting and paging behaviour | rejected (DEC-007) | customer | optional | rejected (DEC-007); not researched or resolved | Rejected by user |
| GAP-016 | Award date, currency and time zone formats | rejected (DEC-007) | customer | optional | rejected (DEC-007); not researched or resolved | Rejected by user |
| GAP-017 | Reports screen content and link to awards | rejected (DEC-007) | customer | optional | rejected (DEC-007); not researched or resolved | Rejected by user |

## 8. Functional Requirements

### Awarding a supplier package

Purpose: a package manager awards a package to one supplier; the award is final.

#### Confirmed requirements

- **FR-901** Award confirmation dialogs must meet WCAG 2.2 AAA and announce every change within 200 milliseconds. [Research: F-GAP-004-01 · Recommended (awaiting approval)]
- **FR-902** The system stores every award note in the audit database, as the mockup shows. [Mockup: SCR-001 · Observed]
- **FR-903** It is confirmed and approved that Add a confirmation step before Award Package is committed, whose text names the package and the supplier being awarded. The related requirement FEA-008 was approved by DEC-008, but the finding itself still carries the label below in the status records, and its source is a low-confidence test fixture. [Research: F-GAP-005-01 · Recommended (awaiting approval)] [Decision: DEC-008]

- **FR-001** Package managers can award a supplier package to one supplier. REQ-001 is approved but still labelled Unknown because eligibility, selection mechanism and permissions are not fully defined (see open items below). [Customer: REQ-001 · Unknown] [Decision: DEC-005]
- **FR-002** A package is awarded to exactly one supplier and the award is final: it cannot be changed or undone by anyone. [Customer: FEA-003 · Explicit] [Decision: DEC-002] [Customer: REQ-001]
- **FR-003** The awarded supplier is chosen from the quotes attached to the package. The recorded interpretation of DEC-001 ("Only suppliers are eligible.") differs from the user's verbatim answer; this specification follows the verbatim. [Customer: FEA-002 · Explicit] [Decision: DEC-001] [Assumption: ASM-G-001]
- **FR-004** Once a package is awarded, no further award attempt on it, whether repeated or made at the same time by someone else, can produce a second or different award. [Customer: FEA-003 · Explicit] [Decision: DEC-002] [Decision: DEC-003]
- **FR-005** The specification must define how a package manager is told apart from other users both when the Award Package action is offered and when an award is carried out. How this is done, and whether other roles may award, is not established. [Customer: FEA-001 · Explicit] [Customer: REQ-001] [Assumption: ASM-G-002]

#### Recommendations awaiting approval

None for this feature area.

#### Open items (undecided)

- **FR-006** Undecided: how the package manager picks the supplier (the captured award form has only an Award note field and an Award Package button), and what happens when a package has no quotes attached while the Award Package button is enabled (PKG-104 shows "No quotes attached yet."). Question Q-002 is open (DEC-011). [Customer: REQ-001 · Unknown] [Customer: FEA-002] [Mockup: SCR-012 · Observed] [Mockup: SCR-003 · Observed]
- **FR-007** Undecided: what the package manager sees while the award processes, when it succeeds and when it fails, and what state the package is left in after a failed award. Question Q-004 is open (DEC-011). The assumption that success moves the package to Awarded with a recorded date is unconfirmed. [Inferred: FEA-009 · Unknown] [Assumption: ASM-F-001 · Assumption] [Mockup: SCR-028 · Observed]
- **FR-008** Undecided: what a user sees when an award attempt is refused because the package is already awarded, and whether repeated supplier emails must be prevented for repeated attempts. [Customer: FEA-003 · Explicit]

#### Acceptance criteria

- **AC-001** (draft) Given an Open package with quotes from suppliers A and B attached and a package manager who has chosen supplier A from those quotes, When the award is committed, Then the package is awarded to supplier A only and the award is final. How the choice is made is undecided (FR-006). [Customer: REQ-001 · Unknown] [Customer: FEA-002] [Decision: DEC-001]
- **AC-002** Given an Open package whose attached quotes are from suppliers A and B and supplier C has no quote attached, When an award to supplier C is attempted, Then no award is made to supplier C. The message shown is not decided. [Customer: FEA-002 · Explicit] [Decision: DEC-001] [Assumption: ASM-G-001]
- **AC-003** Given a package already awarded to supplier A, When any user, including the user who awarded it, attempts to award it again (including to supplier B), Then no second or different award is created and the package remains awarded to supplier A. [Customer: FEA-003 · Explicit] [Decision: DEC-002]
- **AC-004** Given two users have the same Open package loaded, When both submit an award at the same time, Then at most one award exists for the package and the other attempt does not change it. [Customer: FEA-003 · Explicit] [Decision: DEC-002]
- **AC-005** Given an awarded package, When any user attempts to change or undo the award, Then the award stays unchanged. [Customer: FEA-003 · Explicit] [Decision: DEC-002]

### Read-only after award

Purpose: protect the record once the award is made.

#### Confirmed requirements

- **FR-009** Once awarded, a package is read-only for everyone and all of its fields are locked. [Customer: REQ-002 · Approved: DEC-005] [Decision: DEC-003] [Mockup: SCR-015]
- **FR-010** The lock applies to every way the package can be changed, not only to the Award Package button, and no user can lift it. [Customer: FEA-004 · Explicit] [Customer: REQ-002] [Decision: DEC-003] [Decision: DEC-002]

#### Recommendations awaiting approval

None for this feature area.

#### Open items (undecided)

- **FR-011** Not established: whether the lock also covers the quotes attached to the package, and which packages each user can see. [Customer: FEA-004 · Explicit]

#### Acceptance criteria

- **AC-006** Given an awarded package, When a user of any role tries to edit any field of the package by any route, Then the edit is not accepted and every field keeps its awarded value. [Customer: REQ-002 · Approved: DEC-005] [Customer: FEA-004] [Decision: DEC-003]
- **AC-007** (draft) Given an awarded package such as PKG-105, When a user opens it, Then the Award Package button is disabled. The mockup does not explain why; it is assumed to reflect the Awarded status rather than the viewer's permissions. [Mockup: SCR-015 · Observed] [Assumption: ASM-G-003 · Assumption]

### Confirmation before the award

Purpose: reduce accidental, irreversible awards.

#### Confirmed requirements

- **FR-012** A confirmation step comes before the award is committed. It names the package and the supplier being awarded. [Research: FEA-008 · Approved: DEC-008] [Decision: DEC-002] [Research: F-GAP-005-01]
- **FR-013** The confirm control is labelled with the action (for example "Award package") rather than a generic OK. [Research: FEA-008 · Approved: DEC-008] [Research: F-GAP-005-02]
- **FR-014** Because awards cannot be undone, the protection offered is confirmation, not undo. [Research: FEA-008 · Approved: DEC-008] [Research: F-GAP-005-03] [Decision: DEC-002]

#### Recommendations awaiting approval

- **FR-015** Add a confirmation step before Award Package is committed, whose text names the package and the supplier being awarded. The related requirement FEA-008 was approved by DEC-008, but the finding itself still carries the label below in the status records, and its source is a low-confidence test fixture. [Research: F-GAP-005-01 · Recommended (awaiting approval)] [Decision: DEC-008]

#### Open items (undecided)

- **FR-016** Not covered by any source or decision: whether the confirmation also shows value, award note or quote reference. [Research: FEA-008 · Approved: DEC-008]

#### Acceptance criteria

- **AC-008** Given an Open package with a chosen supplier, When the package manager presses Award Package, Then a confirmation naming the package and the supplier is shown and the award is not committed until it is confirmed. [Research: FEA-008 · Approved: DEC-008] [Research: F-GAP-005-01]
- **AC-009** Given the confirmation is shown, When it is displayed, Then its confirm control is labelled with the action (for example "Award package") and not with a generic "OK". [Research: FEA-008 · Approved: DEC-008] [Research: F-GAP-005-02]

### Supplier notification

Purpose: tell the winning supplier about the award.

#### Confirmed requirements

- **FR-017** The winning supplier is emailed at the time the award is made. [Customer: FEA-005 · Explicit] [Decision: DEC-004] [Customer: REQ-003]
- **FR-018** Unsuccessful bidders are not told by the system. REQ-003 still carries the label Unknown in the status records. [Customer: REQ-003 · Unknown] [Decision: DEC-009] [Inferred: FEA-006]
- **FR-019** If the award email cannot be delivered, the failure is shown to staff so they can retry or contact the supplier another way; the award stays in force. [Research: FEA-007 · Approved: DEC-008] [Decision: DEC-002] [Research: F-GAP-004-01]

#### Recommendations awaiting approval

- **FR-020** After Award Package succeeds, if the supplier email fails, show the package as awarded together with a distinct visible warning to the package manager that the email was not delivered, and offer a retry or a way to contact the supplier another way. Naming the package manager as the person who sees the failure is the recommendation's own inference. [Research: F-GAP-004-01 · Recommended (awaiting approval)] [Decision: DEC-008]

#### Open items (undecided)

- **FR-021** Not established: what the award email must contain, where each supplier's email address comes from, and which system sends emails. The user's answer DEC-009 settles the recipients but the item remains labelled Unknown in the status records. [Inferred: FEA-006 · Unknown] [Customer: FEA-005] [Decision: DEC-009]
- **FR-022** Not established: which staff are told of an email delivery failure, how, and how delivery failure is detected. [Research: FEA-007 · Approved: DEC-008]

#### Acceptance criteria

- **AC-010** (draft) Given a package has just been awarded to supplier A, When the award is made, Then supplier A is emailed. The email content is undecided (FR-021). [Customer: REQ-003 · Unknown] [Customer: FEA-005] [Decision: DEC-004] [Decision: DEC-009]
- **AC-011** (draft) Given a package awarded to supplier A that also had a quote from supplier B, When the award is made, Then supplier B is not emailed by the system. [Customer: REQ-003 · Unknown] [Decision: DEC-009]
- **AC-012** Given a package has been awarded and the email to the winning supplier cannot be delivered, When the delivery failure occurs, Then the failure is shown to staff with a way to retry or contact the supplier another way, and the package remains awarded. [Research: FEA-007 · Approved: DEC-008] [Decision: DEC-002]
- **AC-013** (draft) Given the award succeeded and the supplier email failed, When the package manager views the result, Then the package is shown as awarded with a distinct visible warning that the email was not delivered and an option to retry or contact the supplier another way. [Research: F-GAP-004-01 · Recommended (awaiting approval)]

## 9. State Transitions and Edge Cases

### Package lifecycle

| State | Event | Next state | Who can trigger | Provenance |
|---|---|---|---|---|
| Open | Award committed successfully | Awarded (with award date; assumed from PKG-105, transition not shown) | Package manager; other roles Unknown | [Assumption: ASM-F-001 · Assumption] [Mockup: SCR-004 · Observed] [Customer: REQ-001 · Unknown] |
| Open | Award attempt fails | Unknown (state left after a failed award is not decided) | Unknown | [Inferred: FEA-009 · Unknown] |
| Open | Award attempted with no quotes attached | Unknown (not decided) | Unknown | [Customer: FEA-002 · Explicit] [Mockup: SCR-003 · Observed] |
| Awarded | Further award attempt (repeated or simultaneous) | Awarded (unchanged); message shown Unknown | Nobody can change it | [Customer: FEA-003 · Explicit] [Decision: DEC-002] |
| Awarded | Edit of any field | Awarded (unchanged) | Nobody | [Customer: REQ-002 · Approved: DEC-005] [Decision: DEC-003] |
| Awarded | Undo or revoke | Not possible | Nobody | [Customer: FEA-003 · Explicit] [Decision: DEC-002] |
| Any other status value | Any | Unknown (only Open and Awarded are shown) | Unknown | [Mockup: SCR-029 · Observed] |

### Award email lifecycle

| State | Event | Next state | Who can trigger | Provenance |
|---|---|---|---|---|
| Not sent | Award made | Email to the winning supplier sent | System at award | [Customer: FEA-005 · Explicit] [Decision: DEC-004] |
| Email sent | Email cannot be delivered | Failure shown to staff; award stays in force | System | [Research: FEA-007 · Approved: DEC-008] |
| Failure shown | Staff retry or contact the supplier another way | Unknown (retry mechanism and limits not established) | Staff; which staff Unknown | [Research: FEA-007 · Approved: DEC-008] |
| Any | Email to a losing bidder | Not sent | Not applicable | [Customer: REQ-003 · Unknown] [Decision: DEC-009] |

### Edge cases

- Success, duplicates, simultaneous attempts, destructive action, lock and email failure are covered in AC-002 to AC-006 and AC-012.
- Unauthorised access: not specifiable, because roles are not established (FR-005).
- Empty, loading and error states of the award action; invalid or missing Award note: undecided, not shown in the capture (FR-006, FR-007). [Inferred: FEA-009 · Unknown]

## 10. Non-Functional Requirements

- **NFR-001** Data integrity: a package cannot receive a second or different award from repeated, retried or simultaneous attempts. [Customer: FEA-003 · Explicit] [Decision: DEC-002]

No performance, availability, accessibility, security or compliance requirements are justified by the inputs, evidence or decisions. DEC-010 ("Award records are kept for seven years.") is recorded in the Decisions Log but is not linked to any registered item, so no labelled requirement is written for it; see section 16.

## 11. Data Model and Business Rules

No schema or database was inspected. Entities below are what the mockup shows.

- Package: package identifier and title, supplier, value, status (Open, Awarded) are visible. [Mockup: SCR-029 · Observed]
- Award: award date and award note are visible; the awarding user is inferred only. [Mockup: SCR-030 · Observed]
- Quote: contents are not shown (inferred only); the Quotes section is empty on PKG-104. [Mockup: SCR-031 · Observed]
- Relationships (a package has attached quotes and at most one award) follow from the customer's rules, not from an inspected schema.

Business rules:

- **BR-001** A package is awarded to one supplier only. [Customer: REQ-001 · Unknown] [Decision: DEC-002]
- **BR-002** An award is irreversible: it cannot be changed or undone by anyone. [Customer: FEA-003 · Explicit] [Decision: DEC-002]
- **BR-003** An awarded package is read-only for all users and all fields are locked. [Customer: REQ-002 · Approved: DEC-005] [Decision: DEC-003]
- **BR-004** The awarded supplier is chosen from the quotes attached to the package. [Customer: FEA-002 · Explicit] [Decision: DEC-001] [Assumption: ASM-G-001]
- **BR-005** A failed award email does not void or reverse the award. [Research: FEA-007 · Approved: DEC-008] [Decision: DEC-002]

## 12. Screens and User Flows

- Packages list to PKG-104 and PKG-105 via View details; every captured page links to Packages and Reports, and the detail pages also link Back to packages. [Mockup: SCR-018 · Observed] [Mockup: SCR-019 · Observed] [Mockup: SCR-024 · Observed]
- Reports is reachable from every captured page and shows only "Coming soon." [Mockup: SCR-017 · Observed]
- Award Package on PKG-104 has no target in the capture, so the award flow after pressing it is not shown. [Mockup: SCR-028 · Observed]
- Intended award flow (from approved items): package manager opens an Open package, chooses a supplier (mechanism undecided), presses Award Package, sees a confirmation naming package and supplier, confirms, the package becomes Awarded and locked, and the winning supplier is emailed. The steps after confirmation (display, success and failure) are undecided. [Research: FEA-008 · Approved: DEC-008] [Inferred: FEA-009 · Unknown]

## 13. Integrations and Dependencies

- Email: the winning supplier is emailed at award. Where supplier email addresses come from and which sending system exists are not established; no technical documents were supplied. [Customer: FEA-005 · Explicit]
- Delivery failure detection is not established. [Research: FEA-007 · Approved: DEC-008]
- No other integration is established by the inputs.

## 14. Security, Privacy, and Error Handling

- Authorisation: who may award and who may see which packages is not established. [Customer: FEA-001 · Explicit]
- Integrity: awarded packages are locked for everyone and awards cannot be undone. [Customer: REQ-002 · Approved: DEC-005] [Decision: DEC-003]
- Error handling decided: an email delivery failure is shown to staff and the award stays in force. [Research: FEA-007 · Approved: DEC-008]
- Error handling undecided: failure of the award itself and the message for a refused repeat attempt. [Inferred: FEA-009 · Unknown]
- No privacy, audit or accessibility requirement is established by the inputs; the related gaps were rejected (section 3).

## 15. Decisions Log

| DEC | Checkpoint | Decided | Verbatim answer | Interpretation | Items affected | Supersedes / superseded by |
|---|---|---|---|---|---|---|
| DEC-001 | 1 | 2026-10-11T10:36:31Z | "The supplier is chosen from the quotes attached to the package." | "Only suppliers are eligible." (differs from the verbatim; see ASM-G-001) | CQ-001; FEA-002 | none |
| DEC-002 | 1 | 2026-10-11T10:36:31Z | "the award is final; it cannot be undone by anyone" | "Awards are irreversible." | CQ-002; FEA-003 | none |
| DEC-003 | 1 | 2026-10-11T10:36:31Z | "read-only for everyone and all fields are locked" | "Awarded packages are fully locked for all users." (cleared the unknown issue on REQ-002) | CQ-003; REQ-002 | none |
| DEC-004 | 1 | 2026-10-11T10:36:31Z | "Suppliers are notified by email when the award is made." | "Winning supplier is emailed when the award is made." | CQ-004; REQ-003 | none |
| DEC-005 | 1 | 2026-10-11T10:36:31Z | "Everything else is approved as written." | "Approve REQ-001 to REQ-003." | REQ-001, REQ-002, REQ-003 | none |
| DEC-006 | 2 | 2026-10-11T10:41:20Z | "Approve for research only the first two gaps in your table that are routed to research or both, in the order you listed them." | "Approve GAP-004 and GAP-005." | GAP-004, GAP-005 | none |
| DEC-007 | 2 | 2026-10-11T10:41:20Z | "Reject every other gap." | "Reject all other gaps." | GAP-001, GAP-002, GAP-003, GAP-006 to GAP-017 | none |
| DEC-008 | 3 | 2026-10-11T10:48:28Z | "For each question that has a recommendation, take the recommended option." | "Take the recommended option for Q-003 and Q-005." | FEA-007, FEA-008 | none |
| DEC-009 | 3 | 2026-10-11T10:48:28Z | "Suppliers are told by email as soon as the award is confirmed. Bidders who lose are not told." | "Only the winner is emailed, at award." | REQ-003, FEA-006 (Q-001) | none |
| DEC-010 | 3 | 2026-10-11T10:48:28Z | "Award records are kept for seven years." | "Award records are retained for seven years." | none recorded | none |
| DEC-011 | 3 | 2026-10-11T10:48:28Z | "Leave every other question open." | "Q-002 and Q-004 stay open." | Q-002, Q-004 | none |

## 16. Open Questions and Assumptions

| ID | Text | Why it matters | Related items | Impact | Blocking | Owner | Status |
|---|---|---|---|---|---|---|---|
| Q-001 | Who is emailed and what must the email say? | The email is the supplier's only signal about the outcome. | REQ-003, FEA-005, FEA-006 | Recipients answered by DEC-009 (winner only). Email content, address source and sending system remain open; REQ-003 and FEA-006 are still labelled Unknown in the status records. | Recorded as yes in questions.json; not re-assessed after DEC-009 | Customer | Partly answered (DEC-009) |
| Q-002 | How does the package manager choose the supplier, and what happens if no quotes are attached? | The mockup has no supplier control, and an award cannot be undone. | REQ-001, FEA-002 | FR-006 cannot be specified; AC-001 stays a draft. | yes | Customer | Open (DEC-011) |
| Q-003 | Should a confirmation precede the award, and what should it display? | One accidental press is permanent. | FEA-008, F-GAP-005-01 | Answered by DEC-008; value, note and quote on the confirmation are not covered. | no | Customer | Answered (DEC-008); residual in FR-016 |
| Q-004 | What does the user see while the award processes, on success and on failure? | Users must know for certain whether an award went through. | FEA-009, ASM-F-001 | FR-007 cannot be specified. | yes | Customer | Open (DEC-011) |
| Q-005 | What does the package manager see if the supplier email cannot be delivered? | Silent failure could leave the winner unaware. | FEA-007, F-GAP-004-01, REQ-003 | Answered by DEC-008; which staff, how, and detection remain open (FR-022). | no | Customer | Answered (DEC-008); residual in FR-022 |
| OQ-001 | Who may award, whether other roles may award, and who can see which packages? | Controls who can make an irreversible commitment. | REQ-001, FEA-001, FEA-004 | FR-005 and unauthorised-access criteria cannot be specified. | no (not marked blocking in the records) | Customer | Open |
| OQ-002 | What does a user see when an award attempt is refused because the package is already awarded, and must repeated supplier emails be prevented? | Needed to complete the duplicate-attempt behaviour. | FEA-003 | FR-008 cannot be specified. | no | Customer | Open |
| OQ-003 | Does the lock cover the quotes attached to the package? | Defines the extent of the lock. | FEA-004 | FR-011 | no | Customer | Open |
| OQ-004 | To which items does DEC-010 (seven-year retention of award records) apply, and how does it interact with the lock? | DEC-010 has no linked item, so it cannot be labelled or traced. | DEC-010, REQ-002 | No labelled requirement written. | no | Customer | Open |
| OQ-005 | Should the Unknown label on REQ-001, REQ-003 and FEA-006 be cleared after DEC-009 and DEC-005? | The status records still show Unknown, so this specification does not treat these as fully settled. | REQ-001, REQ-003, FEA-006 | Labels in this document follow the status records. | no | Customer | Open |
| ASM-G-001 | The user's verbatim for DEC-001 is followed instead of its recorded interpretation. | The interpretation does not reflect the verbatim. | FEA-002, FR-003, BR-004 | Eligible suppliers are those whose quotes are attached. | no | Customer | Assumption, unconfirmed |
| ASM-G-002 | "Package managers" is a distinct user role in the product. | No role or signed-in user is shown in the capture. | REQ-001, FEA-001 | Permission statements depend on roles existing. | no | Customer | Assumption, unconfirmed |
| ASM-G-003 | The disabled Award Package button on PKG-105 reflects its Awarded status rather than the viewer's permissions. | The capture does not explain why it is disabled. | REQ-002, AC-007 | Treated as the read-only state. | no | Customer | Assumption, unconfirmed |
| ASM-F-001 | A successful award moves the package to Awarded with an award date, as shown for PKG-105. | The transition itself is not shown. | FEA-009, FR-007 | The Open to Awarded transition rests on it. | no | Customer | Assumption, unconfirmed |

No stale items.

## 17. Research Findings and Recommendations

All sources are fixture pages that state they are not real documentation; every finding has low confidence and no publication date.

- F-GAP-004-01: The source states that if a notification cannot be delivered, the failure should be shown to staff so they can retry or contact the supplier another way. Applied to the award flow, the recommendation (FR-020) shows the package as awarded with a visible warning and a retry or alternative-contact option. That the award stays in force comes from DEC-002, not the source. The source does not cover wording, placement, persistence, accessibility or retry limits. Needs confirmation. [Research: F-GAP-004-01 · Recommended (awaiting approval)]
- F-GAP-005-01: The source advises confirming before an action that cannot be undone and stating the consequence, for example which package will be awarded and to whom. Recommendation (FR-015): a confirmation naming the package and the supplier. It does not cover value, note or quote reference. Needs confirmation. [Research: F-GAP-005-01 · Recommended (awaiting approval)]
- F-GAP-005-02: The source advises labelling the confirm button with the action itself (such as "Award package") rather than a generic OK. Advisory only; the exact text is not set by the customer. [Research: F-GAP-005-02 · Research-supported]
- F-GAP-005-03: The source advises not asking for confirmation of easily undone actions and offering undo instead. Because DEC-002 makes awards irreversible, confirmation rather than undo applies; this application is an inference from DEC-002 and supports confirmation only indirectly. [Research: F-GAP-005-03 · Research-supported]

## 18. Sources

| SRC | Title | URL | Publisher | Published | Fetched | Findings | Limitations |
|---|---|---|---|---|---|---|---|
| SRC-b6836a9a | Notifying suppliers of award outcomes (fixture guidance) | https://docs.fixture.example/supplier-notifications | Not recorded | Not available | 2026-10-11 | F-GAP-004-01 | Test fixture, not real documentation; no publication date; robots.txt not checked (fixture mode) |
| SRC-c52222b5 | Confirming irreversible actions (fixture guidance) | https://docs.fixture.example/confirmation-patterns | Not recorded | Not available | 2026-10-11 | F-GAP-005-01, F-GAP-005-02, F-GAP-005-03 | Test fixture, not real documentation; not GOV.UK or Nielsen Norman Group guidance; no publication date; robots.txt not checked (fixture mode) |

### Limitations

Dropped findings are listed only to explain research gaps; none is used as evidence.

- F-GAP-004-02 (Dropped): omitted a qualifying line of its source about unsuccessful bidders, and concerned who is notified rather than how success or failure is shown. 
- F-GAP-005-04 (Dropped): omitted a focus-handling fallback that applies after a successful award, and concerned accessibility implementation detail rather than what the confirmation shows. Its source is SRC-254f3248, which is therefore not used as evidence.
- Research questions left unanswered: established patterns for communicating success and failure of an irreversible action (GAP-004); GOV.UK Design System or Nielsen Norman Group recommendations on confirming irreversible actions (GAP-005); what a confirmation for a contract award should display beyond package and supplier (GAP-005).

```json asm-w
[]
```
