---
name: "obsidian-llm-wiki"
description: "Use when working in the user's Obsidian Agent learning vault and the user asks to ingest sources, query the wiki, lint/maintain the wiki, update Agent learning notes, or apply the LLM Wiki workflow. Reads the project's AGENTS.md, LLM Wiki workflow, source index, and field conventions before editing."
---

# Obsidian LLM Wiki

This skill operates the user's Agent learning Obsidian vault as a persistent LLM-maintained wiki.

## Project

Vault root:

```text
/Users/idah/Projects-combined/obsidian-agentic-learning
```

Main Obsidian folder:

```text
/Users/idah/Projects-combined/obsidian-agentic-learning/agentic learning
```

## Required Context

When this skill triggers, read these files first:

1. `/Users/idah/Projects-combined/obsidian-agentic-learning/AGENTS.md`
2. `/Users/idah/Projects-combined/obsidian-agentic-learning/agentic learning/maps/LLM Wiki 工作流.md`
3. `/Users/idah/Projects-combined/obsidian-agentic-learning/agentic learning/maps/字段规范.md`

Then read the relevant navigation file:

- For source ingestion: `agentic learning/raw/资料收集索引.md`
- For concept work: `agentic learning/maps/Agent 知识地图.md`
- For reading plans: `agentic learning/maps/第一周阅读计划.md`
- For plugin/workflow changes: `agentic learning/maps/学习工作流.md` and `agentic learning/maps/插件配置.md`
- For health checks: `agentic learning/index.md` and `agentic learning/log.md`

## Retrieval Tooling

When working in this vault, prefer the Obsidian hybrid search MCP tools before broad filesystem search:

1. Use `obsidian_status` when tool availability, index freshness, or ignore rules matter.
2. Use `obsidian_search` for concept/topic discovery, related-note lookup, fuzzy title lookup, and semantic recall.
3. Use `obsidian_read` to read exact notes before synthesizing, editing, or citing them.
4. For synthesis, concept comparison, wiki edits, or evidence claims, if `obsidian_read` output is truncated, re-read the core note individually with a larger `snippet_length` or without truncation before making claims.
5. Keep the vault's layer boundary intact: synthesize from `wiki/` and `maps/`; use `raw/` as evidence, not as the first synthesis layer.
6. Fall back to `rg` and direct file reads when MCP is unavailable, stale, or when an exact path/symbol search is narrower.

Do not write runtime details such as proxy settings, model cache paths, local MCP install commands, or local Codex config into durable wiki content.

## Systemic Change Propagation

Before editing, classify the work as simple content work or systemic change.

Simple content work includes one concept card, one source note, one topic-page update, or a narrow typo/link repair.

Systemic change includes any full-batch, incremental-batch, multi-lane, script-driven, schema/template, alias-map, backlink/navigation, raw-ingest policy, concept-card standard, or validation-rule change. For systemic changes, update the affected durable control surfaces before claiming completion:

1. `AGENTS.md` for project-level rules.
2. `agentic learning/maps/LLM Wiki 工作流.md` for workflow rules.
3. `agentic learning/maps/字段规范.md` for schema/frontmatter semantics.
4. `agentic learning/templates/` for reusable page shapes.
5. `scripts/` and alias/config files for automation.
6. Relevant maps, indexes, backlog pages, and `agentic learning/log.md`.

Final reports for systemic changes must state which control surfaces changed, which validation ran, and which surfaces were intentionally left unchanged.

## Bilingual Terminology Audit

Before adding or updating durable concept cards, raw/source concept links, interview-question links, alias maps, or terminology-heavy topic pages, run a Chinese/English terminology gate.

1. Search both the Chinese term and likely English names across `wiki/concepts/`, `wiki/topics/`, `raw/`, `maps/`, `scripts/interview_question_concept_aliases.json`, and `maps/08 面试题概念卡待补充.md`.
2. Choose one canonical concept name before linking. For Agent, RAG, LLM, tooling, evaluation, framework, protocol, retrieval, and memory terms, prefer the stable English term when it is the established paper/docs/community name; keep Chinese terms in `aliases` or link display text.
3. Classify each bilingual pair as exactly one of: existing concept card/add alias only; new concept card with evidence; merge into an existing broader card; backlog candidate because the boundary is uncertain; forbidden mapping/false friend.
4. Do not map a Chinese term to the nearest English card merely because it overlaps. Related is not alias.
5. If a new canonical concept is accepted, synchronize frontmatter `aliases`, `related`, `up`, and `relations`; relevant raw-question `related` and `## 相关知识 wiki`; `scripts/interview_question_concept_aliases.json` when auto-linking should know it; maps/indexes when navigation changes; and `log.md`.
6. Validate with the relevant audit path. At minimum run `git diff --check`; for interview auto-links, also run `python3 scripts/interview_question_concept_links.py --self-test` and a dry run.

## New Concept Mention Backlink Sweep

When creating a new concept card, or when an existing concept gets a new canonical name, major alias, or materially broader boundary, run a mention sweep before claiming completion.

1. Search canonical title, Chinese aliases, English variants, abbreviations, and high-confidence phrase forms across `wiki/concepts/`, `wiki/topics/`, `raw/`, `maps/`, `reviews/`, and relevant automation such as `scripts/interview_question_concept_aliases.json`.
2. Classify each hit before editing: same concept and useful for learning/navigation; raw-source evidence; ambiguous or false friend; already linked/noisy repeat.
3. Link only high-confidence same-concept mentions, usually the first meaningful mention or a local `## 相关知识 wiki` entry. Use display aliases such as `[[Canonical Concept|中文术语]]` to preserve Chinese prose.
4. For raw source evidence, do not rewrite quoted/source text. Prefer `related`, `## 相关知识 wiki`, synthesis notes, or evidence anchors.
5. Put ambiguous, broader/narrower, or false-friend hits into `08 面试题概念卡待补充`, `05 Query 写回队列`, or `06 Wiki 健康检查` instead of forcing weak links.
6. Validate with a search summary and `git diff --check`. If the interview alias map changes, also run `python3 scripts/interview_question_concept_links.py --self-test` and a dry run.

## Operations

### Ingest

Triggered by requests like:

- "ingest this"
- "处理这篇 raw"
- "把这篇资料进 wiki"
- "消化这篇文章"

Workflow:

1. Read the raw source note.
2. Keep raw as evidence; do not turn it into a concept page.
3. Extract key claims, concepts, questions, and boundaries.
4. Before creating or updating `wiki/concepts/` cards, proactively classify each concept's modernity/frontier status using `LLM Wiki 工作流#操作 6：现代性 / 前沿性判定`: foundation, transitional, current-practice, frontier/volatile, or not applicable.
5. Create or update `wiki/concepts/` cards.
6. Update `wiki/topics/`, `maps/Agent 知识地图.md`, and `maps/02 问题池.md` when needed.
7. Update source `status`.
8. Append to `agentic learning/log.md`.

### Concept Card Style

For durable concept cards, prefer the user's learning-card shape:

1. `## 一句话`
2. `## 概念详解` — main body; explain why the concept exists, mechanisms/components, paper/docs/community descriptions, modern-system absorption, and evidence boundaries
3. `## 它解决什么问题`
4. `## 它不是什么`
5. `## 最小例子`
6. `## 常见误解` or `## 风险`
7. `## 边界细节`
8. `## 现代性状态`: proactively judge foundation / transitional / current-practice / frontier / 不适用.
9. When useful, add `## 现代系统怎么吸收 X 的价值` or `## 现代系统怎么吸收 X 的局限`.
10. `## 证据锚点`
11. `## 复习触发`
12. `## 相关链接`

Write cards like `Plan-and-Solve Prompting.md`, but do not stop at structural completeness: for qualified/anchor cards, `## 概念详解` should be the highest-weight explanatory section. Start from the concept's own problem, then use "它不是什么", "常见误解", and "边界细节" to separate it from nearby concepts. The LLM should not wait for the user to ask whether a concept is modern or frontier; when creating or updating a concept, classify it and write the result into `## 现代性状态` or the nearest modern-system section. When the concept comes from a paper-era prompting pattern, agent pattern, or framework pattern, explain how modern systems absorb, constrain, or operationalize it with runtime/tooling/state/evaluation. If a user-provided image is embedded, state whether it is original evidence or a learning/engineering analogy, and add the asset path in evidence anchors.

### Query

Triggered by requests like:

- "基于 wiki 回答"
- "这个概念我该怎么理解"
- "对比 X 和 Y"

Workflow:

1. Start with `index.md`.
2. Read maps and concept cards before raw notes.
3. Use raw notes only as evidence.
4. Answer with Obsidian links.
5. Offer to file durable synthesis back into the wiki when useful.

### Lint

Triggered by requests like:

- "lint wiki"
- "检查知识库"
- "整理一下这个 vault"
- "找孤立页/重复页/缺链接"

Workflow:

1. Check frontmatter.
2. Check raw sources not yet digested.
3. Check concept cards missing boundary sections.
4. Check duplicate concepts and missing links.
5. Apply small safe fixes.
6. Append to log.

## Guardrails

- User-facing wiki prose should be Chinese unless the source title requires English.
- Preserve raw sources unless the user explicitly asks to delete them.
- Prefer small edits and clear links over broad rewrites.
- Do not create concept cards from weak ideas; add weak ideas to `maps/02 问题池.md`.
- Treat user-side intake phrasing, current-task wording, project names, "值得录入", "帮我录入", and similar request-meta as operation context, not knowledge content. Do not write this wording into durable concept cards, topic pages, or source-note synthesis.
- If a paragraph's main job is to say who supplied it, which batch it came from, where to index it, or which frontier judgment to follow, delete it from durable wiki prose instead of rewriting it in place. Keep only neutral evidence, learning value, or write-back metadata.
- Every durable concept should include "它不是什么" or another explicit boundary section.
- Every durable concept should include "边界细节"; for agent/prompting/framework concepts, include how modern systems operationalize or constrain the idea when that helps prevent overgeneralization.
- For Agent, prompting, framework, evaluation, RAG, memory, tooling, safety, protocol, or product-ecosystem concepts, every new or materially updated concept card should include a proactive `## 现代性状态` classification. If classified as frontier/volatile, also consider `03 前沿追踪`, `freshness`, and `last_checked`.
- Use `aliases` only for true aliases of the same concept; use `up` for strict taxonomy and `relations` for typed non-taxonomy relationships. Do not use aliases to hide uncertain or merely neighboring concepts.
- Append log entries; do not rewrite historical log entries.

<!-- skillctl:source-attribution:start -->
## Source Attribution

- origin kind: derived-from-upstream
- upstream repo: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f.git
- upstream path: .
- pinned ref: main
- source type: github
- source URL: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- imported at: 2026-06-14T02:32:13.455Z
- last verified ref: main
- local modifications: true
<!-- skillctl:source-attribution:end -->
