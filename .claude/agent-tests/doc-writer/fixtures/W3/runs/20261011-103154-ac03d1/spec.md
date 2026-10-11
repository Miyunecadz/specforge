# Award Supplier Packages: Feature Specification

## 1. Document Status

- Run ID: 20261011-103154-ac03d1
- Date: 2026-10-11
- Run mode: fixture
- Publication status: pending final pass
- Known limitations:
  - Capture: status complete (4 pages, no failed or skipped pages), but the mockup is static HTML. Only two package pages were captured (PKG-104 Open, PKG-105 Awarded). No loading, error, confirmation or success state for the award action is shown, and the Award Package button on PKG-104 has no target.
  - Research: run in fixture mode. Live search was unavailable and every source is a test fixture page that states it is not real documentation, so all kept findings are low confidence. Two findings were dropped. Several research questions are unanswered (see Sources > Limitations).
  - Gap review: 15 of 17 identified gaps were rejected by DEC-007. Rejection means they were not pursued in this run; it does not mean the behaviour they describe was decided.
- Open stale items: none
- Unresolved blocking issues: Q-002 (how the supplier is chosen, and what happens with no quotes attached) and Q-004 (what the package manager sees during, after and on failure of an award) are open per DEC-011 and recorded as blocking. Q-001 was recorded as blocking; DEC-009 answered recipients and timing, but email content is still undecided.

## 2. Executive Summary

This specification covers one capability: letting package managers award a supplier package to a single supplier. The customer's approved requirements are: package managers can award a package to one supplier (REQ-001), awarded packages are read-only (REQ-002), and suppliers are notified when they win (REQ-003).

The customer has decided that the supplier is chosen from the quotes attached to the package, that an award is final and cannot be undone by anyone, that an awarded package is read-only for everyone with all fields locked, and that only the winning supplier is emailed, when the award is made. The customer also took the recommended options for a confirmation step before awarding and for showing staff when the award email fails, and recorded that award records are kept for seven years.

Key open decisions: how the package manager actually chooses the supplier and what happens when a package has no quotes attached (Q-002); what the package manager sees while an award is processing, when it succeeds and when it fails (Q-004); what the award email must say, where supplier email addresses come from, and how roles are identified. All supporting research is low-confidence test-fixture material and should not be read as an established standard.

## 3. Goals and Scope

### Goals

- Let package managers award a supplier package to one supplier (REQ-001, label: Unknown; approved as written by DEC-005, open issue on supplier selection).
- Make an awarded package read-only for everyone (REQ-002, label: Approved: DEC-005).
- Notify the winning supplier by email when the award is made (REQ-003, label: Unknown; FEA-005, label: Explicit).

### In Scope

- Awarding a package to one supplier chosen from its attached quotes (FEA-002, label: Explicit).
- A final, single award per package (FEA-003, label: Explicit).
- Full lock of an awarded package for all users (FEA-004, label: Explicit).
- Email to the winning supplier at award (FEA-005, label: Explicit).
- A confirmation step before the award is committed (FEA-008, label: Approved: DEC-008).
- Showing staff an email delivery failure (FEA-007, label: Approved: DEC-008).
- Approved gaps: GAP-004 (label: Approved: DEC-006) and GAP-005 (label: Approved: DEC-006), approved for research only.

### Out of Scope / Rejected

DEC-007 rejected every gap other than the two approved for research. "Rejected" here means the gap was not pursued in this run. The behaviour each gap describes is therefore unspecified in this document, not decided, except where another section records a decision.

- GAP-001 Award Package is enabled on a package with no quotes attached (Rejected: DEC-007). The related question Q-002 remains open (DEC-011).
- GAP-002 No way to choose which supplier receives the award (Rejected: DEC-007). The related question Q-002 remains open (DEC-011).
- GAP-003 Who may award, and who may see which packages (Rejected: DEC-007).
- GAP-006 Duplicate and concurrent award attempts (Rejected: DEC-007).
- GAP-007 Notification recipients and content are undefined (Rejected: DEC-007). Recipients and timing were later answered by DEC-009.
- GAP-008 Email delivery failure after an award (Rejected: DEC-007).
- GAP-009 Traceability of who awarded and when (Rejected: DEC-007).
- GAP-010 Award note rules and where the note appears (Rejected: DEC-007).
- GAP-011 How quotes are attached and what they contain (Rejected: DEC-007).
- GAP-012 Package status values and which allow award (Rejected: DEC-007).
- GAP-013 Accessibility of the disabled award button and award status messages (Rejected: DEC-007).
- GAP-014 Retention and deletion of locked awarded packages (Rejected: DEC-007). DEC-010 separately records seven-year retention of award records.
- GAP-015 Package list search, sorting and paging behaviour (Rejected: DEC-007).
- GAP-016 Award date, currency and time zone formats (Rejected: DEC-007).
- GAP-017 Reports screen content and link to awards (Rejected: DEC-007).

No customer requirement excludes anything. Absence from the mockup was not used to infer an exclusion.

### Deferred

No item is deferred: no decision in this run carries a deferral.

## 4. Users and Roles

- Package manager: named in REQ-001 (label: Unknown) as the role that can award. Whether the product has user roles, how a package manager is told apart from other users, and whether a package manager may award any package are not established (FEA-001, label: Explicit; ASM-G-002, label: Assumption). The capture shows no signed-in user or role.
- Other roles that might award: not stated. Unknown.
- Supplier: the recipient of the award email when they win (REQ-003, FEA-005). Suppliers do not appear as users of the captured screens.
- Staff: the audience for an email delivery failure in the approved FEA-007 (label: Approved: DEC-008). Which staff, and how they are told, is not established.
- Who can see which packages: not established.
- Awarded packages are read-only for every user (DEC-003); no role is exempt.

## 5. Existing Mockup Coverage

Capture status is complete: 4 pages captured, 0 failed, 0 skipped, in fixture mode. All observations below are labelled Observed.

| Screen | Name | Observed content | Observed states | Evidence |
|---|---|---|---|---|
| SCR-001 | Supplier packages | Table (Package, Supplier, Value, Status), search box, View details link per row, main navigation (Packages, Reports) | default: PKG-104 Open, PKG-105 Awarded | capture/pages/page-001.txt |
| SCR-002 | Reports | Only the text "Coming soon." under the navigation | empty placeholder | capture/pages/page-002.txt |
| SCR-003 | PKG-104 Kitchen refit | Supplier, value, status Open, Quotes section, Award note textarea, Award Package button (enabled), Back to packages link | Quotes section shows "No quotes attached yet." | capture/pages/page-003.txt |
| SCR-004 | PKG-105 Roof repair | Supplier, value, status "Awarded on 2 Oct 2026", Award Package button (disabled), Back to packages link | disabled button | capture/pages/page-004.txt |

Flows observed: Packages and Reports navigation links work from every captured page (SCR-016 to SCR-027); View details opens PKG-104 (SCR-018) and PKG-105 (SCR-019); Back to packages returns to the list. The Award Package button on PKG-104 has no link or form action (SCR-028, no target).

Observed data: Package with identifier and title, supplier, value, status (Open, Awarded) (SCR-029); Award with award date and award note visible and awarding user inferred, not shown (SCR-030); Quote with contents inferred, none shown (SCR-031).

Ambiguous behaviours the mockup does not answer (carried to Sections 8 and 16 where they matter): who may award; whether the Award note is required or length-limited; confirmation, success and failure display; award with no quotes; which supplier is awarded; why the button is disabled on PKG-105; search and table behaviour (fields searched, sorting, paging, no-results display); all possible Status values; how quotes are attached; Reports contents and access.

Capture limitations: only two package pages; no loading, error, confirmation or success states for the award; static HTML, so button and search behaviour is not shown.

## 6. Requirements Traceability

| REQ | Requirement | Treatment | Label | References |
|---|---|---|---|---|
| REQ-001 | Package managers must be able to award a supplier package to one supplier. | partially addressed | Unknown | DEC-001, DEC-002, DEC-005; FEA-001, FEA-002, FEA-003; FR-001, FR-002, BR-001, BR-002; open Q-002 |
| REQ-002 | Awarded packages should be read-only. | addressed | Approved: DEC-005 | DEC-003, DEC-005; FEA-004; FR-003, FR-004; AC-001, AC-002 |
| REQ-003 | Suppliers must be notified when they win. | partially addressed | Unknown | DEC-004, DEC-005, DEC-009; FEA-005, FEA-006; FR-005, FR-006, BR-003; open email content and address source |

## 7. Gaps Identified

| GAP | Gap | Approval | Path | Priority | Status | Rationale |
|---|---|---|---|---|---|---|
| GAP-004 | Outcome of pressing Award Package is not shown | Approved: DEC-006 | both | critical | open (researched; customer decision pending) | One kept recommendation covers email-failure display (F-GAP-004-01). The research question on success and failure feedback has no source. What the user sees during, after and on failure of an award is open (Q-004, DEC-011). |
| GAP-005 | No confirmation shown before an irreversible award | Approved: DEC-006 | both | critical | addressed (resolved by DEC-008) | DEC-008 took the recommended confirmation naming the package and the supplier (FEA-008). Whether value, award note or quote are shown is not covered by any source and is open. |
| 15 other gaps | See Section 3, Out of Scope / Rejected | rejected (DEC-007) | not applicable | not applicable | not pursued in this run | Listed individually with their Rejected label under Out of Scope / Rejected, which is their only placement in this document. |

## 8. Functional Requirements

### Awarding a package

Purpose: a package manager awards a supplier package to one supplier, and the award is final.

#### Confirmed requirements

- **FR-001** Package managers can award a supplier package to one supplier. Approved as written by DEC-005; the registry keeps an open "unknown" issue on how the supplier is selected (Q-002). [Customer: REQ-001 · Unknown] [Decision: DEC-005] [Mockup: SCR-012]
- **FR-002** Only package managers are required to be able to award. How the product identifies a package manager and whether any other role may award are not established and are not specified here. [Customer: FEA-001 · Explicit] [Customer: REQ-001] [Assumption: ASM-G-002]
- **BR-001** A package is awarded to exactly one supplier, and the award is final: it cannot be changed or undone by anyone. [Customer: FEA-003 · Explicit] [Decision: DEC-002]
- **BR-002** The awarded supplier is chosen from the quotes attached to the package. The recorded interpretation of DEC-001 ("Only suppliers are eligible.") differs from its verbatim; this line follows the verbatim. What a quote contains is not established. [Customer: FEA-002 · Explicit] [Decision: DEC-001] [Assumption: ASM-G-001]
- **NFR-001** Repeated award attempts, and attempts made at the same time by different users, must not produce a second or different award for the same package. The mechanism is not specified. [Customer: FEA-003 · Explicit] [Decision: DEC-002]

#### Recommendations awaiting approval

None of the lines below is confirmed. They are recommendations, assumptions, observations or undecided behaviour.

- **FR-011** Assumed: a successful award moves the package to Awarded and records an award date, as shown for PKG-105. The transition itself is not shown in the mockup. [Assumption: ASM-F-001 · Assumption] [Mockup: SCR-004]
- **FR-012** Undecided: what the package manager sees while the award is processing, when it succeeds and when the award itself fails, and the state the package is left in after a failed award. No kept finding covers this. Open question Q-004 (DEC-011). [Inferred: FEA-009 · Unknown] [Mockup: SCR-028] [Decision: DEC-011]
- **FR-015** Observed: the award form on PKG-104 shows an Award note textarea and an enabled Award Package button, and no control for choosing a supplier. How the supplier is chosen is open (Q-002, DEC-011). [Mockup: SCR-012 · Observed] [Decision: DEC-011]

#### Acceptance criteria

- **AC-007** Given a package that has quotes attached from two different suppliers, When a package manager awards the package, Then the supplier awarded is one of the two suppliers whose quotes are attached. [Customer: FEA-002 · Explicit] [Decision: DEC-001]
- **AC-008** Given PKG-104, which shows "No quotes attached yet." and an enabled Award Package button, When a package manager attempts to award it, Then the outcome is undecided and this criterion cannot be completed until Q-002 is answered. [Customer: FEA-002 · Explicit] [Decision: DEC-011]
- **AC-014** Given a signed-in user who is not a package manager, When they view an Open package, Then the expected outcome cannot be specified, because whether other roles may award and how package managers are identified are not established. [Customer: FEA-001 · Explicit] [Assumption: ASM-G-002]
- **AC-003** Given PKG-105 is already Awarded, When a second award attempt for PKG-105 is submitted, either a repeat by the same user or one made at the same time by another user, Then no second or different award is created and PKG-105 still shows its original award; what the refused user sees is not decided. [Customer: FEA-003 · Explicit] [Decision: DEC-002]
- **AC-004** Given PKG-105 is Awarded, When any user looks for a way to change or revoke the award, Then none is available. [Customer: FEA-003 · Explicit] [Decision: DEC-002]
- **AC-012** (draft) Given a package manager has confirmed an award, When the award is processing, succeeds or fails, Then what is shown, and the state the package is left in after a failure, are undecided (Q-004). [Inferred: FEA-009 · Unknown]
- **AC-013** (draft) Given an award has succeeded, When the package manager views the package, Then it shows status Awarded with an award date, as PKG-105 does. [Assumption: ASM-F-001 · Assumption] [Mockup: SCR-004]
- **AC-015** (draft) Given the Packages list showing PKG-104, When the user selects its View details link, Then the PKG-104 page opens showing supplier, value, status Open, a Quotes section, an Award note field and an enabled Award Package button. [Mockup: SCR-018 · Observed]

### Locking awarded packages

Purpose: once awarded, nobody can change the package.

#### Confirmed requirements

- **FR-003** Awarded packages are read-only. [Customer: REQ-002 · Approved: DEC-005] [Decision: DEC-003]
- **FR-004** Once awarded, a package is read-only for every user and all of its fields are locked. The lock applies to every way the package can be changed, not only the award button, and no user can lift it. Whether the lock also covers the attached quotes is not stated. [Customer: FEA-004 · Explicit] [Decision: DEC-003] [Decision: DEC-002]

#### Recommendations awaiting approval

- **FR-014** Observed: on PKG-105 the Award Package button is disabled. It is assumed this reflects the Awarded status rather than the viewer's permissions; no explanation is shown. [Mockup: SCR-015 · Observed] [Assumption: ASM-G-003]

#### Acceptance criteria

- **AC-001** Given PKG-105 has status "Awarded on 2 Oct 2026", When any user opens it, Then the package is read-only with all fields locked and the Award Package button is disabled. [Customer: REQ-002 · Approved: DEC-005] [Decision: DEC-003] [Mockup: SCR-015]
- **AC-002** Given PKG-105 is Awarded, When any user, including the package manager who awarded it, attempts to change any of its fields by any means, Then the change is refused and the package is unchanged; the message shown is not decided. [Customer: FEA-004 · Explicit] [Decision: DEC-003]

### Supplier notification

Purpose: the winning supplier learns of the award by email.

#### Confirmed requirements

- **FR-005** Suppliers must be notified when they win. Approved as written by DEC-005; the registry keeps an open "unknown" issue (email content and address source). [Customer: REQ-003 · Unknown] [Decision: DEC-005]
- **FR-006** An email is sent to the winning supplier at the time the award is made. Where each supplier's email address comes from, and how emails are sent, are not established. [Customer: FEA-005 · Explicit] [Decision: DEC-004] [Decision: DEC-009]
- **BR-003** Bidders who lose are not told by the system. This is recorded in DEC-009 verbatim ("Bidders who lose are not told."); the registry label for REQ-003 is unchanged by it. [Customer: REQ-003 · Unknown] [Decision: DEC-009]

#### Recommendations awaiting approval

- **FR-013** Undecided: what the award email must contain. [Inferred: FEA-006 · Unknown] [Customer: REQ-003] [Decision: DEC-009]

#### Acceptance criteria

- **AC-005** Given a package manager has awarded a package to a supplier, When the award is made, Then an email is sent to the winning supplier at that time. [Customer: FEA-005 · Explicit] [Decision: DEC-004]
- **AC-006** (draft) Given a package with quotes attached from two suppliers and one of them is awarded, When the award is made, Then no email is sent to the other supplier. [Customer: REQ-003 · Unknown] [Decision: DEC-009]

### Confirmation and failure feedback

Purpose: protect against accidental awards and make email failure visible. Both confirmed lines below were approved by DEC-008, which took the recommended option for Q-003 and Q-005. The research findings behind them remain labelled Recommended (awaiting approval) in the registry, and are shown separately below.

#### Confirmed requirements

- **FR-007** Before the award is committed, a confirmation step is shown that names the package and the supplier being awarded; its confirm control is labelled with the action (for example "Award package") rather than a generic OK. Confirmation, not undo, applies because awards cannot be undone. Whether value, award note or quote are also shown is not covered by any source. [Decision: FEA-008 · Approved: DEC-008] [Research: F-GAP-005-01] [Research: F-GAP-005-02] [Research: F-GAP-005-03] [Decision: DEC-002]
- **FR-008** If the award email cannot be delivered, the failure is shown to staff so they can retry or contact the supplier another way. The award stays in force regardless. Which staff are told, how, and how failure is detected are not established. [Decision: FEA-007 · Approved: DEC-008] [Research: F-GAP-004-01] [Decision: DEC-002]

#### Recommendations awaiting approval

- **FR-009** Recommendation: add a confirmation step before Award Package is committed, whose text names the package and the supplier being awarded. The source does not cover value, award note or quote reference. [Research: F-GAP-005-01 · Recommended (awaiting approval)]
- **FR-010** Recommendation: after Award Package succeeds, if the supplier email fails, show the package as awarded together with a distinct visible warning to the package manager that the email was not delivered, and offer a retry or another way to contact the supplier. The source says "staff"; naming the package manager is the recommendation's own inference. [Research: F-GAP-004-01 · Recommended (awaiting approval)]

#### Acceptance criteria

- **AC-009** Given a package manager is on an Open package with a supplier selected, When they press Award Package, Then a confirmation naming the package and the supplier is shown before the award is committed, its confirm control is labelled with the action (for example "Award package"), and no award is committed until it is confirmed. [Decision: FEA-008 · Approved: DEC-008]
- **AC-010** Given the confirmation is displayed, When the package manager leaves it without confirming, Then no award is committed, so the package is not awarded and no supplier email is sent. [Decision: FEA-008 · Approved: DEC-008]
- **AC-011** Given an award has been made and the email to the winning supplier cannot be delivered, When the failure occurs, Then the failure is shown to staff so they can retry or contact the supplier another way, and the package remains Awarded. [Decision: FEA-007 · Approved: DEC-008] [Decision: DEC-002]
- **AC-016** (draft) Given an award has succeeded and the supplier email then fails, When the package manager views the result, Then the package is shown as awarded with a distinct visible warning that the email was not delivered, plus a retry or alternative-contact option. [Research: F-GAP-004-01 · Recommended (awaiting approval)]

## 9. State Transitions and Edge Cases

### Package lifecycle

| State | Event | Next state | Who can trigger | Provenance |
|---|---|---|---|---|
| Open | Package manager confirms the award | Awarded (with award date) | Package manager; other roles Unknown | [Assumption: ASM-F-001 · Assumption] [Customer: REQ-001 · Unknown] |
| Open | Award attempt fails | Unknown (state after a failed award is not decided) | Unknown | [Inferred: FEA-009 · Unknown] |
| Open | Any other status change | Unknown (only Open and Awarded were observed) | Unknown | [Mockup: SCR-029 · Observed] |
| Awarded | Any attempt to change a field, re-award or revoke | Awarded (unchanged) | No one can change it | [Customer: FEA-004 · Explicit] [Decision: DEC-002] |

### Award notification email lifecycle

| State | Event | Next state | Who can trigger | Provenance |
|---|---|---|---|---|
| Not sent | Award is made | Email to the winning supplier sent | System, at the time of award | [Customer: FEA-005 · Explicit] [Decision: DEC-004] |
| Not sent | Award is made | No email to losing bidders | System | [Customer: REQ-003 · Unknown] [Decision: DEC-009] |
| Sent | Delivery fails | Unknown (failure is shown to staff; further states not decided) | Unknown (detection not established) | [Decision: FEA-007 · Approved: DEC-008] |
| Delivery failed | Staff retry or contact supplier another way | Unknown | Staff; which staff is Unknown | [Decision: FEA-007 · Approved: DEC-008] |

Edge cases and their status:

- Duplicate or simultaneous award: no second award (BR-001, NFR-001, AC-003); what the refused user sees is undecided.
- No quotes attached: undecided (Q-002, AC-008).
- Award fails or is in progress: undecided (Q-004, AC-012).
- Repeated attempts and supplier emails: whether repeated emails must be prevented is not decided.
- Invalid input on the Award note: whether the note is required or length-limited is not stated and not specified here.
- Unauthorised user: not specified (AC-014).

## 10. Non-Functional Requirements

Only NFR-001 (Section 8, Awarding a package) is justified by the inputs. No performance, availability, scalability, accessibility or compliance targets were supplied or researched, and none are invented. Accessibility research was not pursued (see Out of Scope / Rejected).

DEC-010 records "Award records are kept for seven years." It is not linked to any registry item, so it is not written as a requirement line here; see Section 11 and Section 15.

## 11. Data Model and Business Rules

No schema or database was inspected. Fields below are those visible in the mockup or inferred from it.

| Entity | Field | Basis | Evidence |
|---|---|---|---|
| Package (SCR-029) | Package identifier and title | visible | list Package column |
| Package (SCR-029) | Supplier | visible | list Supplier column |
| Package (SCR-029) | Value | visible (currency and format not stated) | list Value column |
| Package (SCR-029) | Status (Open, Awarded) | visible; other values not shown | list Status column |
| Award (SCR-030) | Award date | visible | PKG-105 status line |
| Award (SCR-030) | Award note | visible as an input on PKG-104; not shown on PKG-105 | PKG-104 form |
| Award (SCR-030) | Awarding user | inferred, not shown | not shown; Awarded status implies an award event |
| Quote (SCR-031) | Quote contents | inferred, none shown | "No quotes attached yet." |

Relationships (inferred): a package has zero or more attached quotes (BR-002) and at most one award (BR-001). How a quote relates to a supplier is not established.

Retention: DEC-010 records that award records are kept for seven years. Which records this covers, from when the period runs and what happens afterwards are not stated and are listed in Section 16.

Business rules: BR-001, BR-002 (Section 8, Awarding a package) and BR-003 (Section 8, Supplier notification).

## 12. Screens and User Flows

- Packages list (SCR-001): the entry point; View details opens a package page.
- Package page, Open (SCR-003): shows supplier, value, status, Quotes, Award note and Award Package. Intended award flow: select package, enter optional note (rules unstated), press Award Package, confirmation naming package and supplier (FEA-008, label: Approved: DEC-008), award committed, outcome display undecided (Q-004), winning supplier emailed (FEA-005).
- Package page, Awarded (SCR-004): read-only, Award Package disabled.
- Reports (SCR-002): placeholder "Coming soon."; its relation to awards is not stated and not pursued.
- Navigation: Packages and Reports links on every captured page; Back to packages on package pages.

## 13. Integrations and Dependencies

- Email delivery to suppliers is required (FEA-005, label: Explicit). Which sending system is used, if any exists, is not established; no technical documents were supplied.
- Supplier email addresses: the source is not established; the capture shows only a supplier name.
- Delivery-failure detection: not established (FEA-007).
- No other integrations are known.

## 14. Security, Privacy, and Error Handling

- Authorisation: award is intended for package managers only to the extent REQ-001 says so; role identification and other roles are not established (Section 4). No authentication or permission model was inspected.
- Lock: awarded packages are read-only for everyone (FR-003, FR-004).
- Privacy and compliance: no privacy, regulatory or compliance requirement was supplied or researched. None is claimed.
- Error handling: email delivery failure is shown to staff (FR-008); failure of the award itself is undecided (Q-004); the message for a refused repeat award or refused edit is undecided.

## 15. Decisions Log

| DEC | Checkpoint | Decided | Verbatim answer | Interpretation | Items affected | Supersedes / superseded by |
|---|---|---|---|---|---|---|
| DEC-001 | 1 | 2026-10-11T10:36:31Z | The supplier is chosen from the quotes attached to the package. | Only suppliers are eligible. (differs from the verbatim; this document follows the verbatim, ASM-G-001) | CQ-001 | none |
| DEC-002 | 1 | 2026-10-11T10:36:31Z | the award is final; it cannot be undone by anyone | Awards are irreversible. | CQ-002 | none |
| DEC-003 | 1 | 2026-10-11T10:36:31Z | read-only for everyone and all fields are locked | Awarded packages are fully locked for all users. | CQ-003, REQ-002 (cleared its unknown issue) | none |
| DEC-004 | 1 | 2026-10-11T10:36:31Z | Suppliers are notified by email when the award is made. | Winning supplier is emailed when the award is made. (verbatim says "Suppliers"; clarified by DEC-009) | CQ-004, REQ-003 | none |
| DEC-005 | 1 | 2026-10-11T10:36:31Z | Everything else is approved as written. | Approve REQ-001 to REQ-003. | REQ-001, REQ-002, REQ-003 | none |
| DEC-006 | 2 | 2026-10-11T10:41:20Z | Approve for research only the first two gaps in your table that are routed to research or both, in the order you listed them. | Approve GAP-004 and GAP-005. | GAP-004, GAP-005 | none |
| DEC-007 | 2 | 2026-10-11T10:41:20Z | Reject every other gap. | Reject all other gaps. | 15 gaps, listed under Out of Scope / Rejected | none |
| DEC-008 | 3 | 2026-10-11T10:48:28Z | For each question that has a recommendation, take the recommended option. | Take the recommended option for Q-003 and Q-005. | FEA-007, FEA-008 | none |
| DEC-009 | 3 | 2026-10-11T10:48:28Z | Suppliers are told by email as soon as the award is confirmed. Bidders who lose are not told. | Only the winner is emailed, at award. | REQ-003, FEA-006 (labels unchanged in the registry) | none |
| DEC-010 | 3 | 2026-10-11T10:48:28Z | Award records are kept for seven years. | Award records are retained for seven years. | none recorded | none |
| DEC-011 | 3 | 2026-10-11T10:48:28Z | Leave every other question open. | Q-002 and Q-004 stay open. | Q-002, Q-004 | none |

## 16. Open Questions and Assumptions

| ID | Text | Why it matters | Related items | Impact | Blocking | Owner | Status |
|---|---|---|---|---|---|---|---|
| Q-002 | How does the package manager choose the supplier, and what happens if a package has no quotes attached? | The mockup has no supplier control and the button is enabled with no quotes; awards cannot be undone. | REQ-001, FEA-002 | Award step and its acceptance criteria (AC-008) cannot be completed | Yes (recorded) | Customer | Open (DEC-011) |
| Q-004 | What does the package manager see while the award processes, on success, and when the award itself fails? | Users must know for certain whether an irreversible award went through. | GAP-004, FEA-009, ASM-F-001 | FR-012, AC-012 cannot be completed | Yes (recorded) | Customer | Open (DEC-011) |
| Q-001 (remainder) | What must the award email say? Recipients and timing were answered by DEC-009. | The email is the supplier's only signal of the outcome. | REQ-003, FEA-006 | FR-013 cannot be completed | Q-001 was recorded as blocking; whether this remainder blocks is not recorded | Customer | Partly answered (DEC-009); content open |
| FEA-005 uncertainties | Where do supplier email addresses come from, and how are emails sent? | The email cannot be built without them. | FEA-005, REQ-003 | Notification cannot be implemented as specified | Not recorded | Customer | Open |
| FEA-001 uncertainties | How are package managers identified, may other roles award, and may a package manager award any package? | Controls who can make an irreversible commitment. | FEA-001, ASM-G-002 | FR-002, AC-014 | Not recorded | Customer | Open |
| FEA-004 uncertainties | Does the lock cover attached quotes, and which packages can each user see? | Defines the extent of the lock. | FEA-004 | FR-004 | Not recorded | Customer | Open |
| FEA-003 uncertainties | What does a refused repeat awarder see, and must repeated supplier emails be prevented? | Duplicate attempts cannot be corrected. | FEA-003 | AC-003, NFR-001 | Not recorded | Customer | Open |
| FEA-007 uncertainties | Which staff are told of an email failure, how, and how is failure detected? | Staff cannot act without being told. | FEA-007 | FR-008, AC-011 | Not recorded | Customer | Open |
| FEA-008 uncertainties | Should the confirmation also show value, award note or quote? | Fuller final check versus heavier step; no source covers it. | FEA-008, F-GAP-005-01 | FR-007 | Not recorded | Customer | Open |
| DEC-010 scope | Which records does seven-year retention cover, when does the period start, and what happens after it? | An awarded package is locked for everyone; retention rules must fit that. | DEC-010 | Not specified as a requirement | Not recorded | Customer | Open |
| ASM-G-001 | The verbatim of DEC-001 is taken as the answer, so eligible suppliers are those whose quotes are attached. | The recorded interpretation does not reflect the verbatim. | DEC-001, BR-002 | Eligibility rule | No | Customer | Assumption, to confirm |
| ASM-G-002 | "Package managers" is a distinct user role in the product. | No role is shown in the capture. | REQ-001, FR-002 | Who can award | No | Customer | Assumption, to confirm |
| ASM-G-003 | The disabled Award Package button on PKG-105 reflects its Awarded status, not viewer permissions. | The capture does not explain why it is disabled. | SCR-015, REQ-002 | FR-014 | No | Customer | Assumption, to confirm |
| ASM-F-001 | A successful award moves the package to Awarded with an award date, as shown for PKG-105. | The transition is not shown. | FEA-009, SCR-004 | FR-011, AC-013, Package lifecycle | No | Customer | Assumption, to confirm |

Answered and not repeated above: CQ-001 to CQ-004 (DEC-001 to DEC-004), Q-003 and Q-005 (DEC-008). No stale items.

## 17. Research Findings and Recommendations

All sources are test-fixture pages that state they are not real documentation. Every kept finding is low confidence. Findings are advisory.

| Finding | Label | What the source establishes | How it applies | Recommendation | Limitations |
|---|---|---|---|---|---|
| F-GAP-004-01 | Recommended (awaiting approval) | A notification that cannot be delivered should be shown to staff so they can retry or contact the supplier another way (SRC-b6836a9a). | Applied to the award email. Keeping the package awarded comes from DEC-002, not from the source. | Show the package as awarded with a visible warning to the package manager, and offer retry or another contact route. Needs confirmation; the matching FEA-007 was approved by DEC-008. | Low confidence; no date; says "staff", and naming the package manager is an inference; no wording, placement, persistence or accessibility guidance. |
| F-GAP-005-01 | Recommended (awaiting approval) | Ask for confirmation before an action that cannot be undone and state the consequence, for example which package is awarded and to whom (SRC-c52222b5). | Awards are irreversible per DEC-002. | A confirmation naming the package and the supplier. Needs confirmation; the matching FEA-008 was approved by DEC-008. | Low confidence; no date; covers package and recipient only, not value, note or quote; not GOV.UK or Nielsen Norman Group guidance. |
| F-GAP-005-02 | Research-supported | Label the confirm button with the action, such as Award package, not a generic OK (SRC-c52222b5). | Informs the confirm control label in FR-007. | None. | Low confidence; advisory; exact label text not set by the customer. |
| F-GAP-005-03 | Research-supported | Do not ask for confirmation of easily undone actions; offer undo instead (SRC-c52222b5). | Awards cannot be undone (DEC-002), so confirmation rather than undo applies. This application is an inference. | None. | Low confidence; supports confirmation only indirectly. |

## 18. Sources

| SRC | Title | URL | Publisher | Published | Fetched | Findings | Limitations |
|---|---|---|---|---|---|---|---|
| SRC-b6836a9a | Notifying suppliers of award outcomes (fixture guidance) | https://docs.fixture.example/supplier-notifications | Not recorded | Not available | 2026-10-11T10:41:41Z | F-GAP-004-01 | Test fixture, not real documentation; fixture mode, robots.txt not checked |
| SRC-c52222b5 | Confirming irreversible actions (fixture guidance) | https://docs.fixture.example/confirmation-patterns | Not recorded | Not available | 2026-10-11T10:41:42Z | F-GAP-005-01, F-GAP-005-02, F-GAP-005-03 | Test fixture, not real documentation; fixture mode, robots.txt not checked |

### Limitations

These explain research gaps only and are not evidence.

- F-GAP-004-02 (Dropped): its claim left out the next line of its source, which says whether unsuccessful bidders are notified is a business policy decision, and it mainly concerned who is notified rather than how results are shown.
- F-GAP-005-04 (Dropped): its claim on modal dialog focus left out the source's fallback when the opening control no longer exists, which is the case after a successful award, and it concerns accessibility detail rather than what a confirmation displays.
- Unanswered research questions: patterns for communicating success and failure of an irreversible action (no source found); what GOV.UK Design System or Nielsen Norman Group recommend for irreversible actions (live search unavailable); what a contract-award confirmation should display beyond package and supplier (no source).
- Research was not run for the gaps rejected by DEC-007.

```json asm-w
[]
```
