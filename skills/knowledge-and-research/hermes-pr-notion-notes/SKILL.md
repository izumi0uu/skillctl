---
name: hermes-pr-notion-notes
description: "Use when documenting a NousResearch/hermes-agent issue, PR fix, reviewer-requested revision, or completed upstream change in Notion. Reconstruct the Hermes mechanism and design intent from GitHub and the local worktree, distinguish the original bug, initial approach, review findings, and final fix, then create or idempotently update one evidence-backed Chinese Story per PR in the Hermes PR Notion database."
---

# Hermes PR Notion Notes

## Purpose

把 Hermes PR 从“改了哪些文件”整理成可复用的工程 Story。解释机制为什么存在、故障怎样穿过系统、方案如何演进，以及最终由哪些测试和不变量支撑。

默认写中文，保留代码符号、数据库名和协议名的原文。

## Required Skills And Tools

1. 在执行任何 Notion 写入前，完整读取并遵守可用的 `notion-knowledge-capture` skill。
2. 若需要从本地 Hermes lane、commit 或测试恢复证据，完整读取并遵守可用的 `hermes-upstream-worktree-fix` skill。
3. 优先使用 GitHub MCP；不可用时使用只读 `gh` 命令和本地 Git。
4. 使用 Notion search、fetch、query 和 update/create page 工具；不要通过浏览器手工拼装页面。
5. Notion 工具不可用时停止写入，说明需要连接 Notion；不要创建本地文件冒充已写入笔记。

## Evidence Contract

在写作前建立一份内部 evidence ledger。每个关键结论必须属于以下一种：

- `direct`：由源码、diff、commit、GitHub 评论、测试输出或 Notion 现有字段直接支持。
- `inference`：由多条证据推导，并在正文中使用“说明”“意味着”而非冒充原话。
- `unknown`：无法可靠确定，保留为空或明确记录未知。

至少收集：

- PR 标题、编号、URL、当前状态、author 和 head commit。
- 对应 Issue 的编号和 URL；没有明确关联时保持未知。
- 原始报告的用户症状与可复现条件。
- 修复前的代码路径、数据流或状态机。
- 初版 patch 的策略。
- Reviewer 的原始评论、指出的反例和要求；没有 review 时省略该演进阶段。
- 当前 PR head 的最终实现，不把过时 diff 当成最终状态。
- 实际运行过的测试命令和结果。
- commit authorship；若使用他人的 cherry-pick，保留真实贡献归属。

不要把 PR 描述当作唯一事实来源。使用 current head、base、review threads 和测试互相校验。

## Workflow

### 1. Resolve The Target PR And Repository

- 从用户给出的 PR/Review URL、当前分支或对话上下文确定唯一 PR。
- 确认仓库为 `NousResearch/hermes-agent`；若不是，停止套用 Hermes 专属机制。
- 读取目标 checkout 中的 `AGENTS.md` 和相关局部规则。
- 记录 base SHA、当前 head SHA 和本地分支；不要假设当前目录就是该 PR 的 lane。
- 若本地有未提交改动，只读取并区分其来源，不修改或回滚与笔记任务无关的内容。

### 2. Reconstruct The Change Timeline

按时间顺序区分四层：

1. `original behavior`：Issue 或 PR 最初要解决什么。
2. `initial implementation`：Review 前的方案做了什么、为何看起来合理。
3. `review discovery`：Reviewer 用什么运行时事实或反例发现缺口。
4. `final implementation`：当前 head 如何覆盖初版遗漏，并保持既有设计。

若某层不存在，不要为了故事完整而虚构。尤其不要把最终代码倒推成初版方案。

### 3. Explain The Hermes Mechanism First

先回答“为什么系统本来就这样设计”，再回答“哪里坏了”。至少覆盖与该 PR 相关的：

- 组件职责和 ownership。
- identity、cardinality、lifecycle 和 persistence boundary。
- 正常请求或状态流。
- 必须保持的同步、安全或缓存不变量。
- 两个看似重复的层为何不能直接合并。
- 默认配置和 sibling call paths 是否改变结论。

典型问题包括：

- 为什么同时存在 SessionDB 与 ResponseStore？
- 为什么既有 `os.environ` 又有 profile secret scope？
- 为什么 preflight estimate、provider usage 和 compression verdict 分开维护？

使用至少一个 Mermaid 流程图。只有在确实帮助对比时使用表格或状态矩阵。

### 4. Prove The Failure Chain

写出可以逐步执行的故障链：

```text
输入或前置状态
-> 命中具体分支
-> 某个状态没有同步、被错误覆盖或越过边界
-> 下一层观察到错误状态
-> 用户可见症状
```

指出 bug 发生在什么边界，而不只列出被修改的函数名。说明为何 current main 的正常机制无法自行恢复。

### 5. Explain The Fix As Invariants

不要仅写“增加判断”或“新增测试”。解释：

- 哪一层成为权威 source of truth。
- 新增或收窄了什么显式信号。
- 哪些状态可以 rollback，哪些已经 committed。
- 哪些 path 必须共享相同决策，例如 streaming/non-streaming 或 resolver/credential pool。
- 为何保留 fallback，以及 fallback 防止什么数据丢失或兼容性回归。
- Reviewer 的反例现在由哪条不变量覆盖。

把核心规则写成相等式、布尔条件或状态矩阵，便于以后回归验证。

### 6. Resolve The Notion Destination

按以下优先级确定目标：

1. 用户明确给出的 database/data source。
2. 当前上下文已确认的 Hermes PR 笔记库。
3. 在 Notion 中精确搜索 `Hermes PR 修复笔记库`。

如果搜索结果唯一，直接使用；结果为零或多个时，停止并请求用户指定。不要凭相似标题选择数据库。

先 fetch database 取得最新 schema 和 data source ID，再 query exact numeric PR：

```sql
SELECT * FROM "collection://..." WHERE "PR" = ?
```

- 0 条：创建新 Story。
- 1 条：fetch 当前页面并更新。
- 多条：停止写入并报告重复项。

永远保持“一条 PR 对应一条 Story”。

### 7. Draft The Story

完整读取 [references/story-template.md](references/story-template.md)，按证据选择适用章节。

默认属性映射如下，但必须以 fetch 到的 schema 为准：

- `标题`：`Hermes PR #<number>：<中文主题>`
- `PR`、`PR 链接`
- `Issue`、`Issue 链接`：仅在有直接证据时填写
- `Commit`：使用最终验证过的 head/交付 commit
- `模块`、`标签`
- `状态`、`Review 结论`：只根据 GitHub 当前事实填写
- `修复日期`：使用实际完成日期；未完成时不要伪造

不要修改 database schema 或 select options 来迁就草稿。无法映射的属性保持不变，并把信息写入正文。

### 8. Create Or Update Idempotently

创建时：

- 使用 fetched `data_source_id` 作为 parent。
- 一次创建一页。
- properties 和正文同时提交。

更新时：

- 必须先 fetch 当前页面。
- 保留已有且未被新证据推翻的属性。
- 对正文使用 exact `update_content` replacement；小改动使用最小唯一 anchor。
- 全文重写时，用当前完整正文作为 `old_str`，并在 `new_str` 中保留所有 child page/database 标签。
- 不因当前证据缺失而清空已有 Issue、Commit 或 relation。
- 不删除评论、子页面、数据库或用户手写的相关链接。

写入前检查：标题和正文不重复、来源链接真实、测试数来自实际输出、review quote 没有被改写成 reviewer 原话。

### 9. Verify After Write

写入完成后必须：

1. 重新 fetch 页面。
2. 确认 properties、正文、callout、目录、Mermaid、表格和来源存在。
3. 重新 query data source，确认该 PR 仍然只有一条记录。
4. 确认 child page/database links 没有丢失。
5. 报告页面 URL、数据库 URL、实际写入内容和保留为空的未知字段。

不要仅凭 update API 返回成功就宣称完成。

## Writing Rules

- 面向熟悉工程但未读过该 PR 的读者。
- 先解释机制和设计意图，再解释 bug 和 diff。
- 用具体状态名和数据流，避免“优化了逻辑”“完善了处理”这类空话。
- 将 reviewer 建议写成技术约束，不写成情绪评价。
- 区分“原作者建议已经实现”“只覆盖了一部分”“当前仍未知”。
- 记录测试边界；未运行全量测试时明确写出剩余风险。
- 不泄露 token、secret value、私有路径内容或用户身份信息。
- 不发明 Issue、commit、benchmark、测试数量、合并状态或作者归属。

## Completion Contract

只有同时满足以下条件才算完成：

- Story 能独立解释 Hermes 原有机制。
- 故障链能定位到明确边界。
- 初版、Review 和最终方案没有混写。
- 最终方案以不变量和覆盖路径说明。
- Notion 中按 PR 编号只有一个条目。
- 写后 fetch/query 验证通过。
- 最终回复提供可点击的 database 和 Story 链接。
