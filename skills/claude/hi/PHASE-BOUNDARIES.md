# Phase boundaries in Claude Code

Continue in the current chat when the next phase needs its reasoning or enough context remains. Do not start new chats, copy entire documents, or add approval gates merely because a Skill step ended.

At a meaningful boundary:
1. Continue when current context is useful.
2. If context is irrelevant, let the user start a fresh Claude Code session with `/clear` when appropriate.
3. Use `/handoff` when work must move to another directory, host, tool, or person. Link existing artifacts instead of duplicating them.
4. Use an available, authorized subagent for a bounded independent task. If none is available, continue sequentially.
5. Use the host's supported compaction when needed; do not assume a fixed token threshold or programmatic compaction command. Preserve decisions, unfinished work, and source references.

Never create or message a separate user-visible chat without the user's authorization. Context management is not a reason to repeat a valid design approval.
