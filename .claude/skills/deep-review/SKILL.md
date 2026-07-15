---
name: deep-review
description: Comprehensive code review that checks security, performance, and style in parallel. Use when reviewing staged changes before a commit or PR.
---
Run three parallel subagent reviews on the staged changes:
1. security-reviewer
2. performance-reviewer
3. style-reviewer
Synthesise findings into a single summary with priority-ranked issues. Each issue includes file, line number, and recommended fix.
