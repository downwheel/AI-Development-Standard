# Claude Code skill mechanics

Use SKILL.md YAML frontmatter with name and a clear description. Invoke a skill with `/이름` or the available Skill tool. Keep Korean names matching their directories.

- `disable-model-invocation: true` keeps a skill user-invoked. The other 11 skills may be selected by Claude when relevant. Do not grant broad tool permissions with allowed-tools as part of installation.
- When a user has authorized a multi-step workflow, read cooperating skill files as references within that scope. Do not invent a Skill tool call for a user-only skill or ask the user to invoke every next phase.
- User instructions are in CLAUDE.md. Personal skills are under the current CLAUDE_CONFIG_DIR/skills, default ~/.claude/skills. Read the installed paths exposed in this session.
- Relative reference links resolve against the skill file. Generated work belongs to the configured external Workspace.
- For context management use available Claude Code behavior such as /compact or /clear; preserve decisions first. Delegate only when useful and permitted.
