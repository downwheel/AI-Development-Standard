# Tools connected to project context, design and verification

Choose the capability needed for the task, then a suitable available tool. Read the relevant sections below: project baseline and preview for UI design, documentation for uncertain APIs, and test environment before browser verification. Preserve the design approval boundary in [design-package.md](design-package.md).

## Choose capabilities without adding ceremony

Use the current tool and Skill descriptions to narrow candidates; read the selected Skill before using its tools. Prefer a direct built-in or connected capability that fits the project and the user's choices. Discover additional plugins only when a concrete capability gap warrants it. Installed, connected, authorized, attempted and successfully used are distinct states; an absent immediate tool listing alone does not establish unavailability.

Respect user-disabled or excluded capabilities, including their bundled reference files, even if a cache or broader tool catalog exposes them. In a declared tool-limited environment, use only the offered capabilities. When no permitted design reference is available, create an original visual specification instead of reviving an excluded plugin through cached resources.

| Need | Suitable sources or capabilities |
|---|---|
| Understand an existing UI | Related source, shared components/styles, product documentation, authorized browser or existing design files |
| Establish a new visual direction | Relevant design-reference Skills such as Awesome Design, or an original visual specification |
| Present an editable design | Figma or a local mockup, selected below |
| Resolve an uncertain technical contract | Version-matched documentation, Context7, installed types/source |
| Produce needed visual assets | Existing assets or suitable design/image tools |
| Verify runtime UI | An available browser tool supporting the intended environment |

Load only guidance relevant to the decision. A design-reference Skill can be used through its local resources without an MCP call: read the selected study and turn useful findings into concrete layout, typography or component decisions. Use other installed capabilities when they materially help; calling every plugin or using a fixed number of tools is not a quality goal.

Tool workflows remain within the user's product, stack, storage, approval and publication scope. For example, adding a screen to an existing application does not authorize replacing it with a hosted-site project. Use minimal relevant content and sample data for external design work; a tool connection is not permission to transmit unrelated project data.

## Establish the UI baseline

Classify the work as a new product, an extension of an existing product, or an explicitly requested redesign. Reuse established decisions and investigate only the affected area.

- **Existing product:** identify the closest useful screens and inspect their shared layout, components, styles/tokens, information density, navigation and interaction patterns. Account for relevant themes, localization and role/tenant differences. Compare available runtime evidence with the source; document important uncertainty when access is unavailable. Specify what is reused and what changes. An external design study is unnecessary when existing patterns suffice.
- **New product or approved redesign:** choose a coherent visual direction for the actual audience and task. Use an appropriate installed reference Skill when it helps, such as Awesome Design and a selected study, or develop an original specification when no such resource is available. Explain the resulting decisions rather than listing tool names.

Keep proposed screens consistent with their baseline. Improve in-scope usability defects without reproducing them merely for consistency or expanding into an unrelated redesign. If code, live UI and supplied design disagree, investigate their versions/context and ask only about a material unresolved product choice. A small change following an approved design usually needs no new mockup.

## Select an accessible design deliverable

The user reviews a concrete screen and its behavior, not a required vendor account. Honor an explicit design format or tool preference; otherwise choose by project fit, user access, editability and effort.

| Situation | Design path |
|---|---|
| Figma fits the team's workflow and is available | Reuse its authorized file/library; create or update editable frames and show a preview. |
| No Figma account/access, no design plugin, or local review is preferred | Author a viewable HTML/CSS mockup in Workspace artifacts with an editable source and compact visual specification. Account signup or plugin installation is not a prerequisite. |
| Static views adequately express the decision | SVG/PNG views with editable source and behavior notes are sufficient; distinguish mockups from real-browser captures. |

For an existing product, a focused proposal reusing its layout/components can suffice; recreating the entire application in Figma adds no value by itself. Show the relevant viewports and important states. Keep the preview and written behavior consistent. A tool failure does not remove the need for a viewable proposal, and two parallel Figma/HTML versions are not routinely required.

For Figma, discover the target file/library and actual access, and load the applicable creation/use/design Skills. Create an authorized draft when no file exists instead of asking the user for a URL the agent can obtain. Ask about ownership/access only when a material choice remains. When implementing an approved Figma frame, load the design-to-code Skill and obtain its design context and screenshot before mapping it to the real project's components. Use current authorization for reads and writes separately.

For local design, implement only enough layout and interaction to review the decision, with sample data and no live business writes. Product APIs, persistence and a full implementation remain after design approval. Reusing mockup code later still requires product integration and verification.

Explain a necessary tool substitution briefly and continue within authorization. If Figma itself is an explicit deliverable, a local mockup is interim work until the user agrees to the changed deliverable. Keep a stable reference to the reviewed state; changing tools alone does not require reapproving the same design. No external design writes are performed solely to test Skill installation.

## Version-dependent technical decisions

- Inspect the installed runtime, dependency/lockfile and existing usage first.
- For a library/framework/SDK API whose behavior affects the design or implementation, use Context7 when available: resolve the library identifier, then query the relevant documentation for the installed/target version. Retain a source link and the decision it supports.
- For OpenAI products and APIs, use the installed OpenAI Docs workflow and official sources.
- If Context7 has no applicable coverage or is unavailable, use version-matched primary documentation or installed types/source and state that substitution. A successful lookup for another version does not settle the current API contract.
- Pure business arithmetic and simple standard-language code do not require a Context7 call just to mark a box. Use the source appropriate to any actual uncertainty.

Documentation retrieval supports technical accuracy; it does not replace visual design or user approval. Reuse evidence that is still applicable rather than making the same lookup on every implementation step.

## Select the test environment during design

Reuse the user's designated URL and prior test scope. Inspect the project Harness, existing environment notes, launch configuration and supported preview commands before asking. A configured URL is a candidate, not proof that it is running or is the user's acceptance target.

| Situation | Action |
|---|---|
| New local sample with no specified host | Start a supported local preview within authorization and report its URL; no routine URL questionnaire. |
| A test target is already designated | Reuse it. Clarify only a changed, inaccessible or materially ambiguous environment. |
| Existing application with multiple plausible targets | Present the discovered candidates and recommendation; ask which should be the acceptance target before dependent testing. Continue independent source/design/local work. |
| Login, SSO or VPN needs human action | Use authorized existing access when possible; request only the missing human step. Keep credentials and session material out of chat, design documents and Git. |
| Shared or production target | Respect the agreed read/write/data scope. A URL alone does not authorize deployment, production writes or external messages. |

Group material environment questions with other unresolved requirements, rather than adding an approval stage. In the existing design's verification section, record only applicable details: reference screen, test URL/environment, relevant tenant/role/theme, evidence that the changed code runs there, permitted data operations and remaining access limitations. Reuse project-shared defaults from existing docs and keep personal overrides in external Workspace notes. A simple local sample needs little more than its preview and scope.

Distinguish the URL used to study the existing product from the target used to verify the change. Before claiming runtime verification, establish that the latter runs this work: for example, a task-owned process tied to the checkout, existing build/deployment information, or an identifiable changed behavior. A responding URL or an older server's passing tests is insufficient. If the change is absent or its presence cannot be established, report that coverage accurately, continue authorized local checks, and request only the missing environment/deployment decision. Do not build a new version service or approval ledger for this check.

## Actual UI verification

Use an available browser tool according to its own Skill/instructions on the selected target. Check the approved views, relevant normal/error/empty states, keyboard interaction and critical real-browser behavior. Capture relevant screenshots in Workspace results and compare them with the approved design and existing product baseline. Fix in-scope mismatches; report unrelated pre-existing ones separately.

Cover the affected viewports, roles, tenants and themes rather than every possible combination. Shared layout/style changes warrant representative adjacent-screen checks; an isolated screen change does not automatically require full-product regression. Configure the target once in reusable tests or accept it as input instead of scattering a fixed sample URL throughout them. Retain the actual target and results with the verification evidence.

If browser access fails, inspect the actual error. Resolve supported configuration/preview issues within existing authorization, but never re-expose a denied resource through another route to bypass a security restriction. Continue permitted logic/DOM tests and label their coverage accurately. jsdom or equivalent DOM simulations do not verify CSS layout, mobile rendering, native dialogs or real clipboard permissions. Keep the missing browser/visual checks explicitly unverified until suitable evidence exists.

## Evidence, not tool-count targets

Keep one short table or equivalent notes in the design package; update it with verification evidence when appropriate:

| Purpose | Tool/source | Status | Evidence and effect |
|---|---|---|---|
| Relevant design or technical decision/check | Actual capability selected | used / not applicable / unavailable / planned | Link/path, what was learned or produced; reason and fallback when needed |

Record actual failures as failures; a planned call is not a successful call. Link only the evidence necessary to inspect the decision or check. Do not request separate user approval for every tool call or turn this into a mandatory all-tools checklist.

At design review and completion, briefly tell the user which baseline and selected tools shaped the result, what they produced or changed, and any material substitution or unverified coverage. Keep details in the linked evidence. Reading a reference, creating a mockup and verifying a running screen are different achievements; test counts and tool calls alone do not establish design quality.
