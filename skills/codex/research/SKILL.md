---
name: research
description: 공식 문서, 소스 코드, 규격 등 일차 자료로 질문을 조사한다. 기술적 사실과 API 정보를 확인하거나 배경 조사를 맡겨 출처가 있는 문서를 외부 Workspace에 남길 때 사용한다.
---

Spin up a **background agent** to do the research, so you keep working while it reads.

Its job:

1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not a secondary write-up of them. Follow every claim back to the source that owns it.
2. Write the findings to a single Markdown file, citing each claim's source.
3. Save project research in the configured external Workspace artifacts directory, and report its absolute path. Read existing repository notes as context without automatically relocating them.
