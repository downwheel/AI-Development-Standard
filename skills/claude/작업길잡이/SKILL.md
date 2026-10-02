---
name: 작업길잡이
description: 요청의 목적과 현재 진행 상태를 파악해 적합한 개발 스킬로 연결한다. 요구 확인, 설계, 구현, 오류 진단, 리뷰, 개발 회고 중 어디서 시작할지 선택할 때 사용한다.
disable-model-invocation: true
---

# 작업길잡이

You don't remember every skill, so ask.

A **flow** is a path through the skills. Most paths run along one **main flow**, and two **on-ramps** merge onto it. Everything else is standalone, or a vocabulary layer that runs underneath.

## The main flow: idea → reviewed design → implementation

Route by the impact of the change. Read [design and implementation entry](../설계작성/references/design-package.md) to distinguish new features/material changes, already approved work, small fixes, and design-only requests. Session length does not decide whether design review is needed.

1. **Clarify only unresolved material requirements.** Use `/요구정리` when an interview is useful; reuse existing answers and inspect facts yourself. An approved design can go directly to its implementation path. A small fix can use the lightweight path from the entry reference.
2. **Prepare the concrete design.** For new features/screens or material changes, use `/설계작성` to produce the applicable screen, processing/backend, data and verification design. For UI and version-dependent technology, follow its [tool routing](../설계작성/references/tool-routing.md). A bounded Workspace prototype may resolve a design question; keep the same chat when useful and use `/인수인계` only when portability is actually needed.
3. **Present and obtain one design approval.** Show the package and any required visual proposal together. Requirements answers do not approve an unseen design. Reuse a real approval already covering the work. A design-only request ends here; an implementation request continues once the design is approved.
4. **Implement the approved scope.** Use `/구현` for a small complete unit. For larger work, use `/작업분할` to express the reviewed slices and dependencies, then `/구현` per ticket or `/통합구현` for the graph. Mechanical ticket splitting does not require another approval. Use `/테스트주도` at agreed interfaces and close with `/코드검토`; UI work also needs actual-browser and visual verification.
5. **Learn where useful.** `/개발회고` can inspect a completed or difficult build for concrete environment improvements. When an authorized PR is needed, `/변경요약` shapes its body.

For an end-to-end request, read the cooperating Skills as needed within the already authorized scope; do not ask the user to type each next Skill name. Explicit-only metadata controls discovery, not a requirement for repeated phase-selection prompts. Preserve the design approval boundary above.

### Context hygiene

Keep the requirements and reviewed design available so the interview, spec, and tickets build on the same reasoning. Continue in the current Claude Code chat when useful; use host-managed compaction or a handoff when needed. An implementation can start from its ticket without requiring a fresh chat. Run `/개발회고` with access to the relevant session evidence.

Use the available context indicator to judge when preserving decisions and compacting context is useful; the effective context capacity depends on the model. If a session approaches it before `/작업분할`, preserve the decisions and use supported Claude Code context management at the nearest phase boundary (see Phase boundaries).

## On-ramps

A starting situation that generates work, then merges onto the main flow.

- **Bugs and requests piling up** → **`/요청분류`**. It classifies incoming issues for later work. Before implementation, apply the design-entry rule above; a ready label alone is not design approval.

  Triage is only for issues **you didn't create**: bug reports, incoming feature requests, anything that arrives raw. Tickets that `/작업분할` produced are already agent-ready, so **don't triage them**.

- **Something's broken** → **`/오류진단`**. For the hard ones: the bug that resists a first glance, the intermittent flake, the regression that crept in between two known-good states. It refuses to theorise until it has a **tight feedback loop** (one command that already goes red on *this* bug), then fixes with a regression test. Its post-mortem hands off to **`/구조개선`** when the real finding is that there's no good seam to lock the bug down.

- **A huge, foggy effort: a greenfield project or a huge feature build, too big for one session** → **`/방향탐색`**, the most cognitively demanding flow here. When the way from here to the destination isn't visible yet, it charts a **shared map** of **decision tickets** on the issue tracker and resolves them one at a time, producing **decisions, not deliverables**, until the fog is pushed back and the way is clear. Where **`/요구정리`** sharpens an idea you can hold in one session, wayfinder is for the idea you can't, and it's slower and denser, so save it for exactly that, never a well-scoped feature.

  When the map clears, merge onto the main flow at **`/설계작성`** to assemble the linked decisions into a reviewable design. Reuse an existing approved package when it already covers the work. Create tickets only when the size and dependencies benefit from them.

## Codebase health

Not feature work, just upkeep.

- **`/구조개선`** runs whenever you have a spare moment to keep the codebase good for agents to operate in. It surfaces **deepening opportunities**; picking one _generates an idea_ you can take into the main flow at `/요구정리`. It's the survey that finds the candidates; **`/모듈설계`** (below) is the bench you design the chosen one on.

## Vocabulary underneath

Two model-invoked references that run *beneath* the other skills, each the single source of truth for its vocabulary. Reach for them directly when the **words**, not the process, are the problem; or let the skills above pull them in.

- **`/도메인정리`**: sharpen the project's *domain* language: challenge a fuzzy term, resolve an overloaded word ("account" doing three jobs), record a hard-to-reverse decision as an ADR. It's the active discipline `/요구정리` drives to keep `GLOSSARY.md` a clean glossary.
- **`/모듈설계`** is the deep-module vocabulary (module, interface, depth, seam, adapter, leverage, locality) for designing a module's *shape*: a lot of behaviour behind a small interface at a clean seam. `/테스트주도` and `/구조개선` both speak it.

## Phase boundaries

A **phase** is a chunk of work inside a session: the grilling, the implementation, the QA. At the **boundary** between two of them you have five options, and picking between them is the fuzziest decision in this whole map:

- **Continue**: stay put. Costs nothing, loses nothing.
- **a fresh Claude Code chat**: empty the window, when nothing here matters to what's next.
- **`/인수인계`** writes a portable markdown file. Narrow: only for a **new harness**, a **new directory**, a **colleague**, or forking a side task **mid-phase**. What it buys is portability.
- **Subagent**: send a tightly-scoped task to its own window and get a report back.
- **Claude Code context compaction** summarizes older context so work can continue in the same chat. The **default**, at the bottom of the tree rather than the first reach.

Read [PHASE-BOUNDARIES.md](PHASE-BOUNDARIES.md) for the ordered tree: the five questions, the reasoning behind each branch, and why the primary-source cost makes **Continue** the one to rule out first. Make the decision **at** a boundary; mid-phase, continue or split the rest into subagents.

## Standalone

Off the main flow entirely.

- **`/구상검토`**: the same relentless interview as `/요구정리`, but **stateless**: it saves nothing locally and builds no `GLOSSARY.md`. Reach for it when you are **not working in a working directory** (sharpening a plan, a design, a piece of writing, anything with no repo under it). If you are in a working directory, use `/요구정리` instead: it runs the same interview and leaves a paper trail, so it is strictly the better one.
- **`/심층질문`** is the interview primitive itself: rounds, the frontier, facts are the agent's job and decisions are yours. `/구상검토` and `/요구정리` are the two named ways in, and `/요청분류`, `/방향탐색` and `/구조개선` all run it internally. Reach for it directly only when you want the interview with no wrapper around it.
- **`/시제품`** is a small, throwaway program that answers one design question: does this state model feel right, or what should this UI look like. Throwaway is a constraint on how the code is written, not a promise to destroy it: the answer folds into the real code, and the prototype itself is kept as a **primary source** in the configured external Workspace, referenced from the implementation issue. Use a Git branch only when the user has authorized that workflow. It's the detour in step 2 of the main flow, but reach for it any time a design question is hard to settle on paper.
- **`/자료조사`**: delegate reading legwork to a **background agent**: it investigates a question against **primary sources**, then leaves a cited Markdown file in the configured external Workspace. Keep working while it reads. The file it produces is something to take *into* the main flow at `/요구정리`, since research feeds the thinking rather than replacing it.
- **`/질문서`** comes in when the thing blocking you isn't in your head or the codebase but in **someone else's**, and it writes them a questionnaire to fill in. It's the inverse of `/구상검토`: instead of interviewing you about the subject, it interviews you about the **send** (who it's going to, what you need back) and aims the questions at the gap. What comes back is material for `/요구정리` or `/설계작성`.
- **`/수동안내`** is for the steps only a **human** can take: provisioning infrastructure, setting up credentials or CI secrets, clicking through an unfamiliar third-party dashboard, running a one-off migration or cutover. It generates an interactive bash script that opens each URL, captures each value, and writes it into `.env` and GitHub secrets, so the procedure stops being something you re-explain to an agent every time. Model-invoked, so the agent reaches for it the moment it hits a wall only you can pass. If the agent could just do it itself, it should; this is for where a human is genuinely in the loop.
- **`/쉬운설명`** is the corrective for a message that didn't land. Use it mid-conversation, inside any other skill, and the agent re-pitches what it just said with the context you were missing, in plain English, using the `GLOSSARY.md` vocabulary. It works after the fact; `/요구정리` is the upfront cure, because a shared language agreed early is what stops the jargon arriving at all.
- **`/학습`**: learn a concept over multiple sessions, using the current directory as a stateful workspace.
- **`/지침작성`** is the reference for writing documents agents consume: skills, CLAUDE.md, pointed-at docs.

## Optional project configuration

**`/프로젝트설정`** configures a persistent tracker, label vocabulary and document layout when needed. Existing project bindings or a local external Workspace are enough to start a design or small fix; missing tracker configuration does not block them.
