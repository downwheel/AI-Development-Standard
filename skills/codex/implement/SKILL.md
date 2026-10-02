---
name: implement
description: 승인된 설계나 작업 설명에 따라 하나의 완결된 범위를 구현하고 검사와 코드 검토를 수행한다. 새 기능의 필수 설계가 없으면 먼저 설계 스킬로 연결하고 작은 수정은 간결하게 진행한다.
---

Read [implementation entry and approval](../design/references/design-package.md) before editing. Locate the applicable design and real user decision, or classify a bounded small fix. If required design or approval is missing, read `design` and prepare/present the missing package, then wait for the user's decision before product implementation. Do not re-ask an approval that already covers this work.

Implement the authorized scope. For UI work or unresolved version-dependent APIs, follow [tool routing](../design/references/tool-routing.md); reuse the design's project baseline, selected capabilities and test environment. Resolve only material missing context rather than repeating the design interview.

Use $tdd where possible, at pre-agreed seams.

Run relevant existing tests and checks at useful milestones. Run the applicable suite once at the end; broaden testing when changes, failures or unresolved risks warrant it. For UI, confirm the selected target runs this change, exercise the actual browser and compare with the approved design and existing patterns. Report the actual environment, functional/visual coverage and meaningful tool contribution or substitution; keep the design's current status accurate.

Once done, use $code-check to review the work.

Leave the verified changes available for review. Commit only when the user has explicitly authorized a commit; permission to implement does not by itself authorize commit or push.
