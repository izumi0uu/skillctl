# Hermes PR Story Narrative Toolkit

这不是固定模板。先找到该 PR 最值得学习的因果链，再选择表达方式。不要为了“格式统一”填满章节，也不要虚构 Issue 发现过程、Review、commit 或测试结果。

## The Learning Loop

一篇有效的 Story 应形成学习闭环，但各环节不要求独立成章或按固定顺序出现：

```text
可见信号
-> 可重走的调查路径
-> 调查中揭示的 Hermes 原理
-> 初版采用的系统模型
-> Review 或运行时反例如何修正模型
-> 最终代码怎样表达新模型
-> 测试分别证明什么
-> 可以迁移到未来问题的判断规则
```

没有初版或 Review 时自然省略。简单 bug 可能只需要四个短节；复杂 lifecycle PR 才需要完整演进。

## Choose A Narrative Spine

按证据选择一种主线，也可以混合，但不要机械叠加。

### Symptom-Driven Investigation

适合日志异常、数据丢失、错误状态或用户可复现行为：

```text
现场信号是什么？
-> 最先需要回答的技术问题是什么？
-> 调用链、赋值点或持久化记录怎样缩小范围？
-> 哪些看似合理的原因被排除？
-> 根因最终在哪个边界得到证明？
-> fix 如何改变该边界？
```

### Review-Corrected Mental Model

适合初版合理但遗漏 current-main path、默认配置或并发边界：

```text
初版看到了什么
-> 它依赖什么隐式假设
-> Reviewer 给出哪个真实反例
-> 旧模型为何不足
-> 最终模型如何覆盖完整 bug class
```

### Architecture-Evolution Story

适合 PR 等待期间主线发生变化，或多个 sibling paths 已分化：

```text
原方案针对的旧结构
-> current main 新增了什么 ownership / resolver / lifecycle
-> 为什么旧 patch 仍局部正确但全链路失效
-> 最终如何让共享规则由代码结构保证
```

## Opening Options

选择最能制造具体问题意识的一种开头，不要求统一：

- 一条有辨识度的日志或用户症状。
- 一个 before/after 状态差异。
- 一个看似矛盾的事实，例如“主记录成功，但 late history 丢失”。
- Reviewer 的关键反例，随后回溯初版为何没看到它。
- 一句精确结论，紧跟最短故障链。

避免用 rebase、push、commit 整理或 CI 流水账开头。它们通常不是读者理解 bug 的入口。

## Reveal Hermes Just In Time

Hermes 原理应在它能推进调查时出现。例如：

```text
观察：只有 background review 之后的消息丢失
-> 需要理解 fork 为什么共享父 SessionDB
-> 得出 lifecycle 必须覆盖所有共享写入者
-> 由此发现 run_job 的 finally 不是正确 teardown boundary
```

每段机制解释最好紧接一个用途：排除假设、解释症状、揭示边界、评价初版，或证明最终结构。

不要单独罗列与本问题无关的完整子系统。读者需要的是足够理解这个 PR 的 Hermes，而不是整份架构手册。

## Annotate Symbols And Terms Where They Become Load-Bearing

当一个项目专有工具、函数、类、状态字段、外部产品、协议或系统术语第一次承担因果作用时，紧跟一到三句注解。不要只写“经过 `_some_helper()`”或“使用 Bitwarden”便继续。

代码符号至少让读者知道：

```text
symbol
-> 所属层和调用者
-> 输入、输出或副作用
-> 它在当前故障链中决定了什么
```

外部产品或系统术语则说明其类别、Hermes 的集成方式，以及它在当前问题中决定的边界。无需介绍完整产品历史。

示例：

- `web_extract`：网页正文抽取工具，把 URL 的可读内容交给模型；没有 configured extraction backend 时，它不能提供页面内容证据。
- `_append_guardrail_observation()`：tool-result augmentation helper，把 runtime safety note 附加到本次 tool result，使下一次模型推理可见；它不负责用户最终 footer。
- `previous_response_id`：Responses API 的 continuation pointer，用上一条 response record 恢复下一请求的 history；它不是 Hermes `session_id` 的别名。
- `Bitwarden Secrets Manager`：面向 machine account 的集中式 secret vault；Hermes 启动时通过 `bws` CLI 拉取 project secrets 并注入当前 profile 的 runtime，因此 vault fetch 成功与 profile authorization 是两个不同边界。

只注解当前 Story 真正依赖的符号和术语。不要创建一份与调查分离的大词典，不要对每次重复出现重新解释，也不要根据命名猜实现；注解仍需由源码、schema、协议或 tool contract 支持。成稿中不要出现 `（函数注解）`、`（名词注解）` 等编辑标签。

## Evidence-Aware Discovery Language

把事实来源写清楚：

- Issue 明确记录的过程可以写“报告者观察到……”。
- 根据代码恢复的过程写“从现有证据可以这样重走定位路径……”。
- Git 历史只能证明 patch 演进，不能自动证明作者当时的私人思路。
- 缺少直接证据时，不写“作者先怀疑 X，后来意识到 Y”。

Story 可以有调查感，但不能为了叙事效果制造未经证实的侦查时间线。

## Explain Code As A Model

不要止步于“新增类”“增加判断”。优先展示代码如何编码系统认识：

```text
旧模型：resource lifetime == creator function lifetime
新模型：resource lifetime >= last live user
代码表达：一个 owner 同时持有 agent、DB 和 worker future
```

根据问题选择一种最短表达：

- before/after 流程：适合 ordering 和 ownership。
- 三到五行伪代码：适合 guard、fallback 和 resolver。
- 小型状态矩阵：适合多个互斥状态。
- Mermaid：适合三层以上组件关系或并发分支。
- 短 diff 或关键符号列表：适合局部、直接的修复。

不要同时使用所有形式。一个图已经解释清楚时，不再用长段落重复图中文字。

## Explain Tests As Proof

先写测试证明的行为，再写命令和数量：

```text
`run_one_job` ordering test
-> 证明真实 production orchestrator 保持 delivery < agent.close < DB.close

real SQLite late-write test
-> 证明未完成 worker 的消息确实落盘，而不只是 mock 被调用
```

Pass count、耗时、Ruff 和 CI 是支持证据，不是测试章节的主叙事。未运行的 E2E 或全量测试仍需明确记录。

## Optional Page Elements

按需选用：

- 开头 callout：一句话问题或最终认识。
- 目录：正文确实较长时使用。
- Mermaid：关系难以用短文本表达时使用。
- 表格：需要比较三个以上状态或方案时使用。
- 折叠的“交付记录”：rebase、force-with-lease、CI、commit 整理。
- “可迁移经验”：确实能用于未来 review 时保留；不要生成空泛格言。

## Flexible Example Shape

下面只是一个紧凑示例，不是标题清单：

````markdown
<callout color="blue_bg">
	一条具体日志，以及它真正提出的技术问题。
</callout>

# 从现场信号到根因

展示可见现象、第一条可验证问题和调用链。区分报告者事实与重建路径。

```text
signal -> branch -> wrong state -> downstream symptom
```

# 调查过程中需要理解的 Hermes

只解释推动下一步判断的 ownership、identity、persistence 或 lifecycle 原理，并立即连接回证据。

# 初版为什么合理，又漏掉了什么

写清初版的系统模型、覆盖路径和隐式假设。没有初版演进时省略。

# Review 带来的模型修正

给出 reviewer 的真实反例，以及它怎样推翻旧假设。没有 review 时省略。

# 最终代码如何表达新模型

使用 before/after、伪代码、状态矩阵或 Mermaid 中最合适的一种。

# 哪些测试证明了它

先说明行为契约，再记录实际命令、结果和未覆盖范围。

# 来源

- [PR #<number>](<pr-url>)
- [Issue #<number>](<issue-url>)（若已确认）
- [Review](<review-url>)（若存在）
- 最后核对：<YYYY-MM-DD>
````

允许调整标题、合并章节、从 Review 反例倒叙，或用一张图替代多个段落。判断标准是读者能否顺着证据学会这次定位与修复，而不是页面是否长得像其他 Story。

## Mechanism Depth Checklist

根据 PR 类型选择问题，不要机械逐项写入正文。

### Persistence Or Multiple Databases

- 每个数据库的主键和数据所有权是什么？
- 一对一、一对多还是 derived snapshot？
- 哪个是 durable source of truth？
- 何时同步，失败后如何恢复？
- retention、delete、resume、branch 或 chaining 语义是否不同？

### Profile Or Security Boundary

- scope 由什么 identity 划分？
- process-global compatibility layer 与 scoped authorization layer 如何共存？
- 缺失值应 fallback 还是 fail closed？
- 多 home、并发和同名 key 是否会串值？
- provenance 记录“变量名”还是“当时的值快照”？

### State Machine Or Interrupt

- 哪些状态是 speculative，哪些已经 committed？
- success signal 与 optional telemetry 是否被混为一谈？
- interrupt 能发生在哪些阶段？
- finalizer 可以回滚哪些字段？
- sentinel、counter 和 anti-thrashing state 的职责是否不同？

### Async Or Delivery Lifecycle

- terminal event 在何时 durable？
- `running`、`finalizing`、`delivered`、`failed` 的 ownership 是什么？
- timeout/watchdog 能否与正常 finalization 竞争？
- 哪个状态转换保证 exactly-once 或 recoverable delivery？
- crash/restart 后从哪个 durable record 恢复？

## Property Safety

- 创建页时填写已证实属性。
- 更新页时只修改有新证据的属性。
- 未知值保持空；已有值在未被证伪时保持原样。
- GitHub open/merged/closed 与 Notion `状态` 的映射以现有 schema 和用户约定为准，不自行新增 option。
- `Review 结论=已采纳` 只表示建议已在当前 head 中实现，不代表 PR 已 merge。

## Quality Gate

提交到 Notion 前确认读者能回答：

1. 最初看到了什么具体信号？哪些属于 Issue 直接证据？
2. 从现有证据怎样重走定位路径？哪些私人思考仍未知？
3. 调查需要理解哪些 Hermes 原理，它们如何推进判断？
4. 初版依赖什么系统模型，为什么当时看起来合理？
5. Reviewer 或 current main 提供了什么反例？没有 Review 时，哪个运行时事实完成了模型修正？
6. 最终代码怎样让修正后的模型成为结构性约束？
7. 每个关键测试分别证明哪条行为契约？
8. 删除任意一节后是否更清楚？若不影响学习闭环，就删除或合并。
9. 每个 load-bearing 的项目专有符号、外部产品、协议和系统术语是否在首次出现时获得了足够的行为注解，而不是只留下一个需要读者跳转源码或另行搜索才能理解的名字？
