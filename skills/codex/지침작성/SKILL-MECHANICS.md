# Codex skill mechanics

SKILL.md frontmatter requires name and description. Use agents/openai.yaml for Codex UI metadata and invocation policy.

- For upstream user-invoked workflows, preserve existing `policy.allow_implicit_invocation: false`. The user can select or mention the entry Skill. Within an authorized end-to-end task, a router reads cooperating Skills as needed without asking the user to name each phase; it preserves the applicable design approval boundary. Metadata controls discovery and is not a substitute for task authorization.
- For reusable model-invoked disciplines, preserve `policy.allow_implicit_invocation: true`. Read the discovered SKILL.md and only the needed references when it applies.
- Codex does not require a Claude-specific Skill tool. Use the skill paths exposed by Codex. Read a cooperating skill's instructions through the available file tools.
- A skill instruction cannot grant permissions or tools absent from the current session. Use subagents only when available and authorized; a sequential pass is the fallback where suitable.
- Put substantial conditional guidance in linked references. Keep one authored source for each rule. Apply the writing principles in SKILL.md.
