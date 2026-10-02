---
name: handoff
description: 현재 대화의 결정, 진행 상태, 남은 작업과 참고 자료를 다음 담당자가 이어받을 문서로 정리한다. 다른 사람이나 Agent에게 작업 맥락을 전달할 때 사용한다.
disable-model-invocation: true
---

Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save to the configured external Workspace artifacts directory when working on a project; otherwise use the OS temporary directory. Keep the product source directory clear of handoff files.

Include a "suggested skills" section in the document, naming which skills the next agent should read and follow.

Do not duplicate content already captured in other artifacts (specs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

Redact any sensitive information, such as API keys, passwords, or personally identifiable information.

If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.
