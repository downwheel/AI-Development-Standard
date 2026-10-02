---
name: 작업분할
description: 설계와 요구사항을 의존 관계와 완료 조건이 명확한 구현 작업으로 분할한다. 승인된 설계의 실행 계획이나 설계 검토용 초안을 로컬 파일 또는 허가된 이슈 관리 도구에 작성할 때 사용한다.
disable-model-invocation: true
---

# 작업분할

Break a plan, spec, or conversation into a set of **tickets**: tracer-bullet vertical slices, each declaring the tickets that **block** it.

Read [design approval and change handling](../설계작성/references/design-package.md). Use the existing tracker configuration when available, otherwise local Workspace files. Drafting tickets does not require tracker setup or permission to publish externally.

## Process

### 1. Gather context

Read the supplied design and existing conversation decisions. Preserve a pointer to the design and its user approval on every ticket. If only a plan/conversation or an unapproved design exists, create draft tickets for design review; do not infer implementation approval. Fetch a supplied issue/spec reference and its relevant comments.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Ticket titles and descriptions should use the project's domain glossary vocabulary, and respect ADRs in the area you're touching.

Look for opportunities to prefactor the code to make the implementation easier. "Make the change easy, then make the easy change."

### 3. Draft vertical slices

Break the work into **tracer bullet** tickets.

<vertical-slice-rules>

- Each slice delivers a narrow but COMPLETE behavior through the affected layers and its checks. Do not invent API or database layers that the approved design does not need.
- A completed slice is demoable or verifiable on its own
- Each slice is sized to fit in a single fresh context window
- Include necessary prefactoring in its dependent slice; avoid unrelated cleanup.

</vertical-slice-rules>

Give each ticket its **blocking edges**: the other tickets that must complete before it can start. A ticket with no blockers can start once its design is approved and implementation is authorized.

**Wide refactors are the exception to vertical slicing.** A **wide refactor** is one mechanical change (rename a column, retype a shared symbol) whose **blast radius** fans across the whole codebase, so a single edit breaks thousands of call sites at once and no vertical slice can land green. Don't force it into a tracer bullet; sequence it as **expand–contract**. First expand: add the new form beside the old so nothing breaks. Then migrate the call sites over in batches sized by blast radius (per package, per directory), each batch its own ticket blocked by the expand, keeping CI green batch to batch because the old form still exists. Finally contract: delete the old form once no caller remains, in a ticket blocked by every migrate batch. When even the batches can't stay green alone, keep the sequence but let them share an integration branch that all block a final integrate-and-verify ticket; green is promised only there.

### 4. Reuse the design decision

Summarize each slice's title, delivered behavior, acceptance criteria and blockers. If these mechanically decompose approved work, proceed without another approval round. If the split introduces a material scope/contract/dependency trade-off, include that delta in the design review; keep unaffected approval valid. A user-requested breakdown review still receives the review they asked for.

### 5. Save or publish within authorization

- **Local files**: write one file per useful ticket under `<workspace>/artifacts/<feature>/issues/`, with dependencies in text.
- **Configured remote tracker**: publish only when authorized, using native blocking links where supported. Otherwise keep local drafts ready for publication.

An unapproved design produces `draft` tickets. Use `ready-for-agent` only for an approved scope; dependencies still determine when implementation can start. Apply the project's label mapping if one exists. Neither status automatically closes or changes a parent issue.

Work the **frontier**: any ticket whose blockers are all done. For a purely linear chain that means top to bottom.

Do NOT close or modify any parent issue.

<local-ticket-template>

# <NN>: <Ticket title>

**What to build:** the end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

**Blocked by:** the numbers/titles of the tickets that gate this one, or "None (can start immediately)".

**Design:** <reviewed design link/version and user decision reference, or awaiting review>

**Status:** draft | ready-for-agent (only for approved scope)

- [ ] Acceptance criterion 1
- [ ] Acceptance criterion 2

</local-ticket-template>

<issue-template>

## Parent

A reference to the parent issue on the tracker (if the source was an existing issue, otherwise omit this section).

## Design

The reviewed design link/version and user decision reference, or awaiting review.

## What to build

The end-to-end behaviour this ticket makes work, from the user's perspective, not layer-by-layer implementation.

## Acceptance criteria

- [ ] Criterion 1
- [ ] Criterion 2

## Blocked by

- A reference to each blocking ticket, or "None (can start immediately)".

</issue-template>

Link to the authoritative design instead of copying its contracts into every ticket. Include precise paths or small contract snippets when they clarify actual ownership or acceptance, keeping them consistent with that design.
