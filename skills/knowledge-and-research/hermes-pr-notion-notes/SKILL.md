---
name: hermes-pr-notion-notes
description: "Use when turning a NousResearch/hermes-agent issue, PR fix, reviewer-requested revision, or completed upstream change into an evidence-backed Chinese debugging Story in Notion. Reconstruct how the symptom can be investigated, reveal the relevant Hermes principles as they become necessary, distinguish the initial mental model from review corrections and the final fix, then create or idempotently update one readable Story per PR."
---

# Hermes PR Notion Notes

## Purpose

把 Hermes PR 从“改了哪些文件”整理成可复盘、可学习的 debugging Story。读者应能沿着证据看到：问题如何暴露、怎样从症状缩小范围、调查过程中揭示了哪些 Hermes 原理、初版为何合理但不完整、review 如何修正系统模型，以及最终 fix 和测试如何把新认识编码下来。

这不是固定格式的 PR 报告，也不是脱离问题的架构百科。机制应在它帮助解释下一步调查或设计选择时出现；结构跟随该 PR 最有教育价值的因果链，而不是跟随模板标题。

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
- Issue 作者直接披露的发现线索；没有证据时，不推测其私人思考过程。
- 修复前的代码路径、数据流或状态机。
- 初版 patch 的策略。
- Reviewer 的原始评论、指出的反例和要求；没有 review 时省略该演进阶段。
- 当前 PR head 的最终实现，不把过时 diff 当成最终状态。
- 实际运行过的测试命令和结果。
- commit authorship；若使用他人的 cherry-pick，保留真实贡献归属。

不要把 PR 描述当作唯一事实来源。使用 current head、base、review threads 和测试互相校验。

始终区分三种“发现过程”：

- `reported discovery`：Issue、日志或评论直接说明报告者看到了什么、怎样复现。
- `reconstructed investigation`：根据源码和运行时证据，可以可靠重走的定位路径。
- `private reasoning`：作者当时实际先想了什么、排除了什么；没有直接证据时保持未知，不把重建路径写成作者原话或真实时间顺序。

## Workflow

### 1. Resolve The Target PR And Repository

- 从用户给出的 PR/Review URL、当前分支或对话上下文确定唯一 PR。
- 确认仓库为 `NousResearch/hermes-agent`；若不是，停止套用 Hermes 专属机制。
- 读取目标 checkout 中的 `AGENTS.md` 和相关局部规则。
- 记录 base SHA、当前 head SHA 和本地分支；不要假设当前目录就是该 PR 的 lane。
- 若本地有未提交改动，只读取并区分其来源，不修改或回滚与笔记任务无关的内容。

### 2. Reconstruct The Investigation And Change Timeline

根据证据恢复最有解释力的层次：

1. `observed signal`：最初可见的日志、错误状态、数据差异或用户行为。
2. `investigation path`：从信号追到具体分支、状态变化或 ownership 边界的可复现路径。
3. `initial model and implementation`：初版方案依赖什么系统理解，为何在当时证据下合理。
4. `review correction`：Reviewer 用什么 current-main 事实、生产路径或反例修正了这个理解。
5. `final model and implementation`：当前 head 如何把修正后的模型编码进结构、状态或不变量。

若某层不存在，不要为了故事完整而虚构。尤其不要把最终代码倒推成初版方案，也不要为了制造戏剧性发明“先猜测、再顿悟”的调查过程。

### 3. Reveal Hermes Mechanisms Along The Investigation

不要默认用一大段架构背景开场。先给读者一个具体信号或问题，再在调查需要它时解释相关机制。机制解释只覆盖能够回答以下问题的部分：

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

说明机制后，立即把它连接回当前证据：它排除了哪个假设、暴露了哪个边界，或解释了为何初版 fix 会遗漏 sibling path。

Mermaid、表格、状态矩阵、伪代码和纯文本流程都只是表达工具。只在它们比短段落更清楚时使用；不要强制每篇 Story 都有图或矩阵。

### Annotate Project-Specific Symbols And Load-Bearing Terms At First Use

不要假设函数名、状态字段、内部类名、Hermes 工具名、外部产品、协议名或基础设施术语能够自解释。一个符号或名词第一次成为理解故障链所必需的节点时，就地给出一到三句注解。

对代码符号至少回答：

- 它属于哪一层或由哪个组件调用。
- 它接收或观察什么，产生什么状态变化、返回值或副作用。
- 它为什么与当前 issue 的下一步调查、Review 反例或最终不变量有关。

对外部产品、协议和系统术语至少回答其中适用的部分：

- 它属于什么类别，在 Hermes 调用链中扮演什么角色。
- Hermes 通过什么接口、进程或持久化层与它交互。
- 该术语在当前 bug 中决定了哪个 ownership、security、lifecycle、caching 或 evidence boundary。

例如，首次出现 `web_extract` 时，应说明它把 URL 对应的网页正文抽取成模型可读取的文本，缺少 extraction backend 时不会提供页面证据；首次出现 `_append_guardrail_observation()` 时，应说明它把 runtime guardrail 文本附加到 tool result，让下一次模型调用看到，而不是直接修改用户最终回复。首次出现 `Bitwarden Secrets Manager` 时，应说明它是面向 machine account 的集中式 secret vault；Hermes 启动时通过 `bws` CLI 和 access token 拉取 project secrets，再把 provider key 引入当前 profile 的运行时，因此“值已加载”仍不等于“当前 profile 已获授权”。

注解应贴着第一次有意义的使用出现，不要把所有名词移到开头做脱离上下文的百科。常见协议名或已经在相邻段落清楚定义的符号不必重复解释；同一个符号后续只沿用简称。函数名本身只能证明 identity，不能替代行为说明。

不要在成稿中保留 `（函数注解）`、`（名词注解）`、`（状态字段注解）` 之类的编辑标签。读者应该直接读到自然解释，而不是看到模板的内部标记。

### 4. Make The Investigation Reproducible

写出读者可以根据证据重走的路径。根据实际材料，可能包括：

- 什么异常现象让某个组件成为怀疑对象。
- 怎样沿调用链、状态赋值、日志或持久化记录缩小范围。
- 哪些看似合理的原因被源码事实排除。
- 最终在哪个 lifecycle、identity、persistence、security 或 caching boundary 证明根因。

故障链通常可以压缩为：

```text
输入或前置状态
-> 命中具体分支
-> 某个状态没有同步、被错误覆盖或越过边界
-> 下一层观察到错误状态
-> 用户可见症状
```

指出 bug 发生在什么边界，而不只列出被修改的函数名。说明为何 current main 的正常机制无法自行恢复。

如果调查顺序来自重建而非作者直接记录，明确写成“从现有证据可以这样重走定位路径”，不要写成“作者先发现……随后意识到……”。

### 5. Explain The Fix As A Corrected System Model

不要仅写“增加判断”或“新增测试”。先指出初版和最终版分别依赖什么系统模型，再解释：

- 哪一层成为权威 source of truth。
- 新增或收窄了什么显式信号。
- 哪些状态可以 rollback，哪些已经 committed。
- 哪些 path 必须共享相同决策，例如 streaming/non-streaming 或 resolver/credential pool。
- 为何保留 fallback，以及 fallback 防止什么数据丢失或兼容性回归。
- Reviewer 的反例现在由哪条不变量覆盖。

当代码引入 owner object、状态字段、resolver、guard 或新的调用结构时，说明它如何让正确模型变得难以被未来改动拆散。核心规则可以写成相等式、布尔条件、短伪代码、before/after 流程或状态矩阵，选择最贴合该问题的一种即可。

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

完整读取 [references/story-template.md](references/story-template.md)。它是 narrative toolkit，不是必须逐项填写的页面骨架。先选择该 PR 最有教育价值的主线，再选用必要模块；小修复可以很短，复杂 review 演进可以更长。

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

写入前检查：标题和正文不重复、来源链接真实、测试数来自实际输出、review quote 没有被改写成 reviewer 原话。rebase、push、force-with-lease、commit 整理和瞬时 CI 状态默认放到属性、来源或简短交付附录；除非它改变了实现或证据，不要让它们占据摘要和主叙事。

### 9. Verify After Write

写入完成后必须：

1. 重新 fetch 页面。
2. 确认 properties、正文、来源以及本篇实际使用的 callout、目录、Mermaid 或表格正确渲染；未选择的元素不要求存在。
3. 重新 query data source，确认该 PR 仍然只有一条记录。
4. 确认 child page/database links 没有丢失。
5. 报告页面 URL、数据库 URL、实际写入内容和保留为空的未知字段。

不要仅凭 update API 返回成功就宣称完成。

## Writing Rules

- 面向熟悉工程但未读过该 PR 的读者。
- 优先让读者跟随问题调查；在需要时解释机制，不做与定位无关的架构前言。
- 结构服务于因果链。不要因为前一篇用了九个章节、Mermaid 或状态矩阵，就在下一篇机械复用。
- 用具体日志、状态赋值、调用链、diff 片段或测试断言承载关键转折；抽象结论要紧邻其证据。
- 项目专有函数、内部状态字段、类、工具，以及承担因果作用的外部产品、协议和系统术语，在首次承担叙事作用时必须有就地注解；不能只留下名称让读者自行搜索其职责。
- 用具体状态名和数据流，避免“优化了逻辑”“完善了处理”这类空话。
- 解释初版为何合理时，指出它依赖的假设或心智模型；不要把 review 后的知识强加给初版作者。
- 将 reviewer 建议写成技术约束，不写成情绪评价。
- 不把测试章节写成 pass count 清单；先说明每个关键测试证明了哪条行为契约，再记录命令和范围。
- 动态 CI 状态很快过时。正文只在它对结论必要时记录，并带查询时间；稳定的行为证据优先于瞬时交付状态。
- 区分“原作者建议已经实现”“只覆盖了一部分”“当前仍未知”。
- 记录测试边界；未运行全量测试时明确写出剩余风险。
- 不泄露 token、secret value、私有路径内容或用户身份信息。
- 不发明 Issue、commit、benchmark、测试数量、合并状态或作者归属。

## Completion Contract

只有同时满足以下条件才算完成：

- Story 能独立解释理解该 PR 所必需的 Hermes 机制，不要求扩展成完整子系统文档。
- 关键项目符号与 load-bearing 外部/系统术语在首次承担因果作用时已有行为注解，读者不需要仅凭命名猜测其职责、输入/输出、副作用或系统角色。
- 读者能从原始信号重走一条有证据的调查路径，并知道哪些步骤是重建而非作者原始叙述。
- Hermes 原理与当前调查或设计选择直接相连，而不是泛泛的背景介绍。
- 初版的心智模型、Review 反例和最终修正没有混写。
- 最终代码如何表达修正后的模型，以及关键测试分别证明什么，均已说明。
- Notion 中按 PR 编号只有一个条目。
- 写后 fetch/query 验证通过。
- 最终回复提供可点击的 database 和 Story 链接。
