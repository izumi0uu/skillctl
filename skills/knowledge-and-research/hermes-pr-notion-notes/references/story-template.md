# Hermes PR Story Template

按证据选用章节。不要为了填满模板而虚构 Issue、Review、commit 或测试结果。

## Recommended Page Shape

````markdown
# 摘要

[PR #<number>](<pr-url>) 修复了 <用户可见症状>。根因是 <机制边界上的状态错误>；最终通过 <核心不变量> 修复。

<callout color="blue_bg">
	**最终效果：**<一句话描述修复后的稳定行为和不会再发生的失败。>
</callout>

<table_of_contents/>

# 1. Hermes 的相关机制与设计意图

## 1.1 <组件 A>：<职责>

说明 ownership、identity、durability 和调用者。

## 1.2 <组件 B>：<职责>

说明它与组件 A 看似重叠但不能合并的原因。

## 1.3 两者如何协作

```mermaid
flowchart LR
    INPUT["输入"] --> A["组件 A"]
    A --> B["组件 B"]
    B --> OUTPUT["持久化或输出"]
```

# 2. 正常运行流与不变量

```text
normal_state_before
-> operation
-> authoritative_state_after
```

列出必须成立的 equality、scope、ordering 或 lifecycle 规则。

# 3. 原始 Issue / 问题如何暴露

说明环境、触发条件、用户症状和为什么日常测试此前没有覆盖。

```text
前置状态
-> 触发分支
-> 错误状态
-> 下游后果
-> 用户症状
```

# 4. 根因

指出错误的 source of truth、隐式假设或跨层同步缺口。不要只写函数名。

# 5. 初版修复与思路

说明初版为什么合理、覆盖了哪种模式、还依赖什么假设。

# 6. Review 如何发现缺口

没有 Review 证据时省略本节。

## 6.1 <反例或默认路径>

引用或准确转述 reviewer 的技术要求，并连接到真实 runtime path。

## 6.2 <第二个边界条件>

说明新增测试为何能暴露旧方案。

# 7. 最终修复

## 7.1 <显式信号或权威状态>

说明最终代码如何表达事件边界。

## 7.2 <所有 sibling paths>

说明 streaming/non-streaming、profile/cron、success/no-usage 等相关路径如何统一。

## 7.3 <兼容 fallback>

说明 fallback 保护的旧行为以及何时生效。

# 8. 最终状态矩阵或同步不变量

<table fit-page-width="true" header-row="true">
<tr>
<td>场景</td>
<td>预期行为</td>
<td>原因</td>
</tr>
<tr>
<td>正常路径</td>
<td>...</td>
<td>...</td>
</tr>
<tr>
<td>边界路径</td>
<td>...</td>
<td>...</td>
</tr>
</table>

# 9. 回归覆盖与验证

- `<实际命令>`：`<实际结果>`
- 未运行或不可验证的范围：<明确写出>

# 10. 设计结论

1. <可复用的不变量>
2. <不要再依赖的隐式信号>
3. <未来 sibling path 的评审规则>

# 来源

- [PR #<number>](<pr-url>)
- [Issue #<number>](<issue-url>)（若已确认）
- [Review](<review-url>)（若存在）
- 最后整理：<YYYY-MM-DD>
````

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

1. Hermes 为什么需要这些组件或状态？
2. 正常情况下数据如何流动？
3. 原问题在哪个边界暴露？
4. 初版为什么没覆盖完整 bug class？
5. Reviewer 的反例是什么？
6. 最终修复建立了什么不变量？
7. 哪些测试证明了这些不变量？
