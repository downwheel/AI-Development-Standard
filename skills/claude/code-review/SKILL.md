---
name: code-review
description: 요청한 코드 변경을 저장소 규칙 준수와 요구사항 및 설계 충족의 두 관점으로 검토한다. 브랜치, 변경 제안, 현재 미커밋 작업의 결함과 검증 누락을 확인할 때 사용한다.
disable-model-invocation: false
---

Two-axis review of the change scope requested by the user, including uncommitted work when reviewing the current implementation:

- **Standards**: does the code conform to this repo's documented coding standards?
- **Spec**: does the code faithfully implement the originating issue / spec?

Use **parallel sub-agents** for the two axes when available and authorized. Otherwise perform two distinct sequential review passes and identify that limitation; creating extra agents is not a prerequisite for reviewing a small change.

Use the available project standards and local or remote design evidence. Missing tracker configuration does not block a review. For design applicability and approval, consult [design-package.md](../design/references/design-package.md); UI or version-dependent checks also use [tool-routing.md](../design/references/tool-routing.md).

## Process

### 1. Pin the fixed point

Choose the actual requested scope before collecting evidence:
- For a committed branch/PR, resolve the requested base (or the known PR base) and use `git diff <base>...HEAD` plus the commit list.
- For work-in-progress, include `git diff`, `git diff --cached`, and relevant untracked files reported by `git ls-files --others --exclude-standard`. Read untracked file contents; a branch-only diff does not include them.
- When both committed and working-tree changes belong to the request, include both. Keep pre-existing user changes identifiable and do not assign them to this implementation automatically.
- If no base was supplied for a current uncommitted edit, review that edit rather than asking for an unnecessary commit. Ask only when the intended scope is materially ambiguous.

Confirm that the chosen inputs contain the actual implementation. Record the compared paths and commands for both review passes. An unborn repository can still have untracked work to review.

### 2. Identify the spec source

Look for the originating spec, in this order:

1. The reviewed design/package and actual user decision provided in the task or conversation, including its linked visual proposal.
2. A path the user supplied or a spec under the project's recorded document locations, `docs/`, `specs/`, or the external Workspace artifacts.
3. Relevant issue references fetched through the configured tracker, when available and authorized.
4. For a small fix with no standalone spec, use the user request and clear existing behavior as the review contract. If essential requirements remain unavailable, identify the missing evidence; ask only if the user can resolve it. Do not create a new design/approval flow merely to conduct a read-only review.

For new features/material changes, report a missing design approval as a process finding; do not manufacture one from the implementation. For UI, compare actual-browser results with the approved design and applicable existing-screen patterns. Check that evidence comes from the intended environment running this change, including relevant role/theme context. Treat DOM-only checks, an older deployment or unconfirmed code provenance as limited coverage. Check claimed tool use against its outputs and effect; omission of an irrelevant plugin is not a finding. Include functional, visual and access limitations in the Spec result rather than adding an automatic third reviewer.

### 3. Identify the standards sources

Anything in the repo that documents how code should be written, such as `CODING_STANDARDS.md` or `CONTRIBUTING.md`.

On top of whatever the repo documents, the Standards axis always carries the **smell baseline** below: a fixed set of Fowler code smells (_Refactoring_, ch.3) that applies even when a repo documents nothing. Two rules bind it:

- **The repo overrides.** A documented repo standard always wins; where it endorses something the baseline would flag, suppress the smell.
- **Always a judgement call.** Each smell is a labelled heuristic ("possible Feature Envy"), never a hard violation. Like any standard here, skip anything tooling already enforces.

Each smell reads *what it is* → *how to fix*; match it against the diff:

- **Mysterious Name**: a function, variable, or type whose name doesn't reveal what it does or holds. → rename it; if no honest name comes, the design's murky.
- **Duplicated Code**: the same logic shape appears in more than one hunk or file in the change. → extract the shared shape, call it from both.
- **Feature Envy**: a method that reaches into another object's data more than its own. → move the method onto the data it envies.
- **Data Clumps**: the same few fields or params keep travelling together (a type wanting to be born). → bundle them into one type, pass that.
- **Primitive Obsession**: a primitive or string standing in for a domain concept that deserves its own type. → give the concept its own small type.
- **Repeated Switches**: the same `switch`/`if`-cascade on the same type recurs across the change. → replace with polymorphism, or one map both sites share.
- **Shotgun Surgery**: one logical change forces scattered edits across many files in the diff. → gather what changes together into one module.
- **Divergent Change**: one file or module is edited for several unrelated reasons. → split so each module changes for one reason.
- **Speculative Generality**: abstraction, parameters, or hooks added for needs the spec doesn't have. → delete it; inline back until a real need shows.
- **Message Chains**: long `a.b().c().d()` navigation the caller shouldn't depend on. → hide the walk behind one method on the first object.
- **Middle Man**: a class or function that mostly just delegates onward. → cut it, call the real target direct.
- **Refused Bequest**: a subclass or implementer that ignores or overrides most of what it inherits. → drop the inheritance, use composition.

### 4. Spawn both sub-agents in parallel

**Standards sub-agent prompt** should include:

- The full diff command and commit list.
- The list of standards-source files you found in step 3, **plus the smell baseline from step 3** pasted in full (the sub-agent has no other access to it).
- The brief: "Report, per file/hunk where relevant, (a) every place the diff violates a documented standard: cite the standard (file + the rule); and (b) any baseline smell you spot: name it and quote the hunk. Distinguish hard violations from judgement calls: documented-standard breaches can be hard, but baseline smells are always judgement calls, and a documented repo standard overrides the baseline. Skip anything tooling enforces. Under 400 words."

**Spec sub-agent prompt** should include:

- The diff command and commit list.
- The design/request, its user decision when applicable, linked visual target and actual functional/browser evidence. Distinguish planned checks from executed ones.
- The brief: "Report missing/partial requirements, scope creep and incorrect behavior against the supplied design/request. For UI, compare the actual rendered evidence with the reviewed visual target and identify missing checks as unverified rather than passed. Cite the source of each finding. Under 400 words."

If no usable requirements source exists, report Spec as unverified; the absence of a standalone spec file alone does not prevent reviewing a clear small-fix request.

### 5. Aggregate

Present the two reports under `## Standards` and `## Spec` headings, verbatim or lightly cleaned. Do **not** merge or rerank findings, because the two axes are deliberately separate (see _Why two axes_).

End with a one-line summary: total findings per axis, and the worst issue _within each axis_ (if any). Don't pick a single winner across axes: that's the reranking the separation exists to prevent.

## Why two axes

A change can pass one axis and fail the other:

- Code that follows every standard but implements the wrong thing → **Standards pass, Spec fail.**
- Code that does exactly what the issue asked but breaks the project's conventions → **Spec pass, Standards fail.**

Reporting them separately stops one axis from masking the other.
