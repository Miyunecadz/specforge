# Gap checklist (BUILD_SPEC §14)

A **discovery aid, not a feature list.** For each item, the gap-analyst asks: does this
product's mockup or requirements leave a decision open here that matters for *this*
feature? Raise a gap only when the answer is yes, and explain why it is relevant to this
product (field `checklist_item` names the item; `why_it_matters` gives the product-specific
reason). An item with nothing to say is skipped silently. Never report an unobserved
feature as definitively absent: a state or screen that was not captured is unobserved.

Each item lists prompts to check, not features to add.

1. **Authentication and accounts:** sign-in required for this feature? Behaviour for
   signed-out users, account states (suspended, invited, deleted).
2. **Roles, permissions, data visibility:** who may view, create, change, approve,
   delete; whether visibility differs by role, team, tenant or ownership.
3. **Empty, loading, success and error states:** for each screen or list in the flow:
   what is shown with no data, while loading, after success, on failure.
4. **Form validation and messages:** required fields, formats, limits, cross-field rules,
   where and how errors are shown, what happens to entered data on error.
5. **Search, filter, sort, pagination:** behaviour with many records, defaults, empty
   results, whether criteria persist.
6. **Notifications and delivery failure:** who is told what and when, through which
   channel, and what happens if delivery fails.
7. **Settings:** per-user or per-organisation options the feature implies.
8. **Admin and back-office:** who can correct mistakes, override, or manage reference data.
9. **Audit logging:** whether actions must be traceable (who, what, when, before/after).
10. **Import and export:** formats, size limits, partial failures, permissions.
11. **Accessibility (WCAG 2.2 AA where relevant):** keyboard use, focus, labels, contrast,
    status messages, timing.
12. **Responsive and mobile:** layouts and interactions at small sizes; touch targets.
13. **Internationalisation:** languages, dates, numbers, currency, time zones, text length.
14. **Privacy and consent:** personal data collected or shown, purpose, consent, minimisation.
15. **Onboarding:** first-use experience, empty starting states, guidance.
16. **Help and support:** where users get help, contact paths, in-product guidance.
17. **Poor connectivity and recoverability:** slow or lost connections, retries, drafts,
    resuming interrupted work.
18. **Destructive-action confirmation and undo:** irreversible actions, confirmation,
    undo windows, recovery.
19. **Duplicate submissions:** double clicks, repeated requests, two people acting at once.
20. **Session expiry and permission changes:** what happens mid-task when a session ends or
    a user's role changes.
21. **Data lifecycle, deletion, retention:** how long records live, who can delete, what
    happens to related records.
22. **Concurrent changes and conflict handling:** two users editing the same record;
    stale views; locking or merge rules.
23. **Rate limits and external-service failures:** dependencies that can be slow, limited
    or down, and what users see.
24. **Retries and idempotency:** which operations may be retried safely; what prevents
    double effects.
25. **Operational visibility:** what support or operations staff need to see to diagnose
    problems with this feature.
