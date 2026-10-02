---
name: integrate
description: 승인된 설계의 여러 작업을 의존 순서에 따라 구현하고 통합한다. 기존 승인을 재사용하면서 기능 검사, 실제 화면 검증, 전체 변경 검토까지 조율할 때 사용한다.
---

# integrate

Complete the authorized design across its task graph. Read [implementation entry and approval](../design/references/design-package.md) before any product edits. Read the design, its real user decision, and each ticket's scope. A ready label or a directly invoked implementation Skill does not substitute for that review. If design or approval is missing, use `design` to prepare and present the missing package first.

Use the configured tracker if present, otherwise local Workspace tickets. If the approved work has no tickets yet, derive them with `tickets`; mechanical decomposition does not require another approval. One small unit can use `implement` without creating a graph.

## Execute the graph

1. Establish acceptance criteria, dependencies and source ownership. Pass the approved design and applicable [project/tool/test-environment evidence](../design/references/tool-routing.md) to implementers as pointers, not duplicated specifications.
2. Choose the execution mode using actual authorization and isolation needs. Sequential work in the current checkout is sufficient when shared changes or Git permissions make branch integration unsuitable. Parallel subagents are useful for independent slices when available and authorized; provide each the approved scope, dependencies and verification obligations.
3. For a branch integration workflow, create only authorized branches/worktrees, use the intended integration base and preserve existing user changes. Commit, merge, push, issue updates and PR publication stay within their respective user authorization. Without that workflow, leave a verified working-tree diff and do not describe it as merged work.
4. Work the frontier: implement only units whose dependencies are satisfied. Each implementer follows `implement` and `tdd` at the agreed public interfaces. Reuse design approval; escalate only material changes to the reviewed behavior/contracts as described in the entry reference.
5. Integrate completed slices and run relevant integration checks. Confirm that the selected UI test target runs the integrated change; compare real-browser evidence with the approved design and existing product baseline. Scope adjacent-screen/theme checks to the impact of shared changes.
6. Use `code-check` on the actual combined change scope. Fix in-scope findings and rerun affected checks. Report implemented behavior, actual test environment, functional/visual coverage, meaningful tool contribution and remaining blocks; update the design's current status.
7. Update external issues or PR state only when authorized. Retire only task-owned worktrees no longer used by any process, preserving changes through the host's managed lifecycle. Report the integration branch only if that workflow actually ran.

Keep unaffected work moving when a material design decision blocks another slice. Do not ask the user to approve each task start, test run, generated file or session transition.
