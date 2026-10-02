---
name: design
description: 새 기능, 화면, 주요 동작이나 데이터 변경 전에 검토 가능한 설계 패키지를 작성한다. 필요한 화면 시안, 처리와 백엔드, 데이터, 검증 계획을 함께 제시하고 사용자 승인을 받을 때 사용한다.
disable-model-invocation: true
---

# design

Turn the agreed requirements into a concrete design the user can review. Reuse facts and decisions already established; ask only about unresolved choices that materially change the result.

Read [design-package.md](references/design-package.md) for applicability, approval, change handling, and the package contents. Read [tool-routing.md](references/tool-routing.md) when selecting design/documentation tools or planning UI verification.

## Process

1. **Locate the work.** Inspect the relevant source, project Harness, existing designs and applicable conventions. Distinguish a new product, an existing-product extension and a requested redesign; identify the existing-screen baseline when applicable. Reuse an existing approved package when it covers this change. A request for analysis or design alone ends with that deliverable.
2. **Design the affected layers.** Prepare one concise package in the configured external Workspace. Include a viewable UI proposal for UI work, processing/backend contracts, data changes when needed, and a verification plan. Document why a layer is unchanged or unnecessary instead of inventing infrastructure. Distinguish user decisions from proposed defaults.
3. **Choose suitable capabilities.** Follow the tool-routing reference: existing product patterns first, useful design references for unresolved visual decisions, an accessible Figma or local preview, and version-matched documentation for technical uncertainty. Select relevant available tools without requiring every plugin. Include actual outputs and their implications.
4. **Check readiness.** Resolve choices discoverable from the environment, including the intended UI test target and how to confirm the change runs there. Ask only about material unresolved choices, reusing prior answers. Include useful implementation slices when needed. Make the design, preview and verification expectations accessible together; identify limitations plainly.
5. **Present for one design decision.** Link/open the package and visual preview, summarize its scope and how the baseline/selected tools shaped it, and request approval of that concrete package. Requirements answers alone do not approve an unseen design. Until this decision, keep work to investigation, design and bounded Workspace prototypes; leave product implementation for after approval.
6. **Record and continue within authorization.** Record the real user response and covered scope in the same package. If the user authorizes implementation, continue with `implement`, or `tickets` and `integrate` for a larger task. Approval already present in the conversation is reused; do not request it again merely to change Skills or create tickets. A design-only request does not authorize implementation.

## Storage and publication

Use existing project document locations when present; new AI design artifacts follow the external Workspace policy. Default to a local package when no tracker is configured. Tracker setup, labels, glossary and ADR creation are not prerequisites for drafting or reviewing the design.

Publish to a remote issue tracker only within the user's actual publication authorization. Keep a draft local otherwise. Design completion does not automatically apply `ready-for-agent`; readiness depends on the approved scope and resolved dependencies. No separate approval service, source snapshot, or document copy is required for each step.
