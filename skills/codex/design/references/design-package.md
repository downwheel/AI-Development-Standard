# Design package and implementation entry

Use this reference before product implementation and when preparing or reviewing a design. It defines one design decision for the affected work, not a sequence of approvals for individual files or tools.

## Choose the path by the change

| Situation | Action |
|---|---|
| New feature/screen, major UI interaction, public interface/data/security change | Prepare and present a design package before implementation, even if the work fits one session. |
| Existing approved design covers the requested implementation | Read it and its user approval; continue within that scope without another review ceremony. |
| Typo, small adjustment following the existing design, localized bug restoring a clear existing contract | Briefly explain the bounded change and verify it. A new package, mockup or tool call is unnecessary. |
| Analysis, review, design-only or a requested exploratory prototype | Produce that deliverable; no automatic promotion to product implementation. |

Classify by behavior and impact, not file count or session length. If a localized fix reveals a new product decision, design and review that affected part. This applies when entering through `implement`, `integrate`, `tdd`, bug diagnosis or a ticket as well as through `hi`. Naming an implementation Skill or marking a ticket ready does not establish design approval.

## Prepare a concrete package

Use one main document, usually `<workspace>/artifacts/<feature>/design.md`. Split only detail that materially improves review. Link existing artifacts instead of copying them. All paths are resolved using the project binding and the user's Workspace configuration.

The package should let the user assess the following:

| Part | Include when applicable |
|---|---|
| Scope and acceptance | The problem, intended behavior, short user flows, measurable completion criteria and exclusions. Avoid long story lists that repeat the same behavior. |
| UI design | A viewable proposal linked to its editable source; the existing-screen baseline and reused patterns, or the proposed new visual direction. Include layout, components, field rules, actions, relevant states and viewport behavior. Account for affected themes/localization/roles without enumerating unrelated combinations. |
| Processing/backend | Where processing runs; responsibilities; concrete request/response or local function contracts; validation, error behavior, authorization and external dependencies. Explain when no backend is needed. |
| Data | Existing object impacts and, when changing storage, fields/types, keys/constraints, transaction behavior, migration/backfill and recovery. Explain when no database change is needed. |
| Verification | Existing commands, agreed public test interfaces, independent expected results, failure cases and browser/visual checks. For UI, identify the reference screen, intended test environment and how to confirm the changed code runs there; include relevant account/theme/data scope and access limits. Distinguish live-service checks from local checks. |
| Implementation scope | Affected areas and dependencies; include precise paths, schema fragments or examples when they clarify an actual contract. For larger work, include the proposed slices here. |
| Decisions and evidence | Separate user-confirmed choices, agent-proposed defaults and unresolved questions. Link documentation/design evidence with the decision it supports. |

For new or major UI, prose or a list of controls alone is insufficient. Provide an accessible preview with editable source. Follow [tool-routing.md](tool-routing.md) to select the project baseline, suitable design capability and test environment. Figma and local mockups are valid paths; an account or plugin is not a design prerequisite. Honor an explicitly required deliverable. If no viewable proposal is available, identify the limitation instead of declaring the UI design ready.

Only investigate factual uncertainties yourself. Collect remaining material product questions together rather than interviewing again about settled requirements. An irrelevant layer receives one brief reason, not an empty standalone document.

## One approval and bounded changes

1. Present the package and visuals together, with a clear scope and any remaining limitations. Request one decision on that concrete design.
2. A response such as “권장안대로 만들어줘” to requirements questions settles those requirements; it does not approve UI or contracts that have not been shown. A response such as “이 설계대로 구현해” after the package was presented authorizes implementation within it.
3. Reuse approval already given for the presented design, including across Skills or sessions. Use the conversation or a preserved reference to a real user decision. An assistant-authored `approved` label alone is not evidence; resolve genuinely missing approval context without recreating a review the user already completed.
4. Store a short review entry in the existing design document: the reviewed package/version, covered scope, actual user response/reference, and outcome. Keep proposed defaults distinguishable until the package is approved. Do not create a new copy, hash-based lease, ledger or approval server for routine changes.
5. After approval, proceed autonomously with implementation details, tests and fixes that preserve the reviewed behavior. Ticket splitting, formatting, internal refactoring and moving to another Skill are not fresh approval events.
6. For a material change to the reviewed UI flow, public contract, data model, permissions or operating cost, present only the affected design delta and its impact. Keep unaffected approval valid; continue independent authorized work while a necessary decision is pending. Preserve a concise record of what changed instead of rewriting prior approval as if it covered the new scope.

Design approval does not imply permission to commit/push, publish issues, deploy, change production data or send messages. Honor existing authorization for those actions separately. A prototype is a bounded design experiment stored in Workspace artifacts, not the full unapproved product under another filename.

## Review entry example

```text
Design: <path/link and recognizable reviewed version>
Scope: <covered behavior and relevant screens/contracts>
Review: awaiting decision | approved | changes requested
User decision: <actual response and conversation reference, when present>
Subsequent material change: <only if one occurred; affected approval status>
```

The example is a small record, not a new mandatory schema. If equivalent information already exists, reuse it. Approval is a cooperative workflow rule, not an OS-level enforcement mechanism.

## Completion evidence

Compare the finished implementation to the accepted behavior, visible design and applicable existing product patterns. A new UI is fully verified only when functional and required browser/visual checks have evidence from an environment confirmed to run the changed code. Unit tests, DOM simulations and a `code-check` pass cannot establish visual fidelity or real browser permissions.

If verification is blocked, report what passed, what remains unverified and the concrete reason. Keep UI verification incomplete while continuing independent authorized checks. Do not repeatedly ask for a design approval to compensate for a tool failure.

Keep the document's current implementation and verification status up to date. Preserve useful earlier evidence as dated history, not contradictory present-tense status. Use the existing document rather than creating another status file or approval record.
