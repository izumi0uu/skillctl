---
name: recruitflow-project-ops
description: Use when the task is about RecruitFlow or its Project-Plan workspace inside `/Users/idah/Projects-combined`. This skill onboards the agent into the RecruitFlow document flow, Jira operating model, branch-pack reading order, and project-specific editing rules.
---

# RecruitFlow Project Ops

## Overview
- Use this skill only for the current RecruitFlow project system inside `/Users/idah/Projects-combined`.
- This skill is project-specific. It should not be reused for unrelated repositories.
- It exists to reduce startup ambiguity: which docs to read, which rules win, when Jira matters, and which project-specific boundaries apply.

## Project Boundary
- In scope:
  - `/Users/idah/Projects-combined/RecruitFlow`
  - `/Users/idah/Projects-combined/Project-Plan`
- Out of scope:
  - unrelated repositories under other roots
  - future projects that need their own entry workflow
- If a future project needs a similar setup, create a separate skill such as `$project-name-project-ops` instead of reusing this one.

## Trigger Phrases
- `Use $recruitflow-project-ops`
- `RecruitFlow project entry`
- `Load RecruitFlow project rules`
- `Onboard into RecruitFlow before coding`

## Workflow

### 1. Identify Task Type
- Determine whether the task is primarily:
  - code implementation
  - planning or documentation
  - Jira management
  - branch handoff or review
- Use that classification to decide which docs are mandatory.

### 2. Respect Git Sync Ownership
- This skill does not require a clean working tree check before code edits.
- Run repository sync or rebase operations only when the user explicitly requests them; follow that repository's documented Git workflow directly.
- If the working tree is dirty, work with existing changes and do not revert user work.
- Preserve manual git publishing ownership unless the user explicitly asks for commit, push, or PR actions.

### 3. Read the Minimum Shared Context
- Before implementation, read:
  - `Project-Plan/main-plan.md`
  - `Project-Plan/00-overview/domain-glossary.md`
  - `Project-Plan/01-shared-specs/data-model-v1.md`
  - `Project-Plan/01-shared-specs/runtime-boundaries.md`
  - `Project-Plan/01-shared-specs/language-conventions.md`

### 4. Load Jira Context When the Task Touches Execution Tracking
- If the task mentions stories, blockers, branch execution, status updates, handoff, or Jira:
  - read `Project-Plan/02-jira-ops/jira-operating-model.md`
  - read `Project-Plan/02-jira-ops/phase-1-story-index.md`
  - read `Project-Plan/02-jira-ops/phase-1-relationship-map.md`
- Use Jira as the live source of truth for current status and links.
- Use `Project-Plan/02-jira-ops/*` as the durable operating handbook.

### 5. Sync Live Jira State Before Implementation
- Before implementation or progress reporting begins, query the real Jira issue for:
  - current status
  - current assignee when relevant
  - recent comments
  - current `Blocks` links
  - available transitions if a status change may be needed
- Treat Jira as the default live execution truth.
- Use the branch pack and repository state to validate or challenge that truth, not to silently replace it.
- If the repository appears ahead of Jira:
  - do not silently continue as though Jira were current
  - add a Jira comment that explains the observed implementation reality
  - say what appears done, what still needs verification, and what remains before full completion
- If the repository appears behind Jira:
  - do not trust ticket state alone
  - verify the required code path before reporting progress or completion
- If active implementation truly begins after this sync, comment and move the issue to `In Progress` when the workflow supports it.

### 6. Read the Target Branch Pack
- Once the target branch or module is known, read that branch pack in this order:
  1. `README.md`
  2. `contracts.md`
  3. `jira-stories.md`
  4. `implementation-plan.md`
  5. `qa-checklist.md`
  6. `handoff.md`

### 7. Check Story-to-Blocker Order Before Implementation
- Before treating any story as the next formal implementation target, check:
  - Jira `Blocks` relationships when available
  - explicit story dependencies in the branch pack
  - branch ownership and shared-contract prerequisites
- Do not start a blocked story just because:
  - the missing UI is obvious
  - the work feels smaller or easier
  - the current code gap is visually prominent
- A blocked story can be started only if:
  - its blockers are already satisfied in code, even if Jira is slightly stale, or
  - the user explicitly approves out-of-order scaffold work
- If you do out-of-order work, label it clearly as:
  - preparatory scaffold work
  - partial shell work
  - not full story closure yet
- Do not report a blocked story as fully completed until its blocker chain is actually satisfied.

### 8. Use the Story Deviation Protocol When Reality Differs From the Plan
- Default mode is story-first execution.
- If reality forces a deviation, classify it before proceeding:
  - `incidental fix`
  - `minimal unblocker`
  - `partial scaffold work`
  - `cross-contract deviation`
- `incidental fix`, `minimal unblocker`, and `partial scaffold work` may proceed only if:
  - they stay within current branch ownership
  - they do not silently rewrite shared contracts
  - they are reported clearly afterward
- `cross-contract deviation` must stop and wait for explicit user approval before implementation.
- Never silently drift from the active story just because:
  - the missing UI is obvious
  - the adjacent work looks easy
  - the framework pushes in a different direction

### 9. Write Back to Jira During Execution, Not Only at the End
- For any meaningful implementation step, keep Jira current with English comments.
- Required write-back moments include:
  - real implementation start
  - deviation from default story order
  - discovery of a new blocker or contract mismatch
  - handoff-ready checkpoint
- If repository reality differs from Jira, write that mismatch back before or alongside the next progress update.
- For every deviation, write back:
  - deviation type
  - reason
  - what was done
  - what remains before full completion
- Update status when needed:
  - move to `In Progress` when actual implementation begins
  - change status again only through real Jira transitions
  - do not guess transition ids
  - do not leave Jira stale when execution reality has clearly changed

### 10. Update Project-Plan Selectively, Not By Default
- `Project-Plan` is a durable execution record, not a line-by-line mirror of every code edit.
- Do not update `Project-Plan` by default for ordinary implementation work.
- Update `Project-Plan` only when at least one of these is true:
  - the user explicitly asks for plan or documentation updates
  - a new Jira story, dependency, or blocker relationship is being added or materially changed
  - a branch-pack execution fact has changed in a way that future agents must rely on, such as:
    - new accepted scope boundary
    - new shared contract or route ownership rule
    - new durable QA requirement
    - new handoff-ready story state that is not already reflected in the branch pack
  - a shared spec truly changed and the code now depends on that new shared rule
- Do not update `Project-Plan` for:
  - routine code implementation with no contract or scope change
  - isolated UI polish, copy changes, spacing changes, or visual tuning
  - local refactors that do not change branch execution reality
  - PR-only, commit-only, or publish-only requests
- When a `Project-Plan` update is justified:
  - keep the write scope minimal
  - prefer the current branch pack first
  - update shared specs only when the rule is genuinely cross-branch
  - mention in the final summary why the plan update was necessary
- If `Project-Plan` is already dirty with unrelated edits, do not expand or rewrite those files unless the current task truly requires it.

### 11. Respect Document Priority
- If sources conflict, use this priority:
  1. `01-shared-specs/*`
  2. live Jira state plus `02-jira-ops/*`
  3. the relevant branch pack
  4. `main-plan.md`
  5. `99-archived/*`
- Never implement from `main-plan.md` alone when shared contracts or branch packs exist.

### 12. Preserve RecruitFlow-Specific Language
- Active planning docs are English-only.
- Archived files may remain in their original language.
- Keep technical identifiers aligned with the project system:
  - branch names
  - route names
  - entity names
  - enums
  - Jira key format

### 13. Prefer Reusable UI Components
- When planning or implementing UI work, first inspect the existing component system and page-local components for reusable pieces.
- Prefer existing components for common UI primitives and patterns, including:
  - buttons
  - modals/dialogs
  - cards
  - form fields
  - dropdowns/menus
  - tabs
  - tables/lists
  - empty, loading, and restricted states
- Do not introduce new raw HTML-heavy structures when an existing component or composition pattern can express the same behavior.
- Add new UI components only when:
  - no suitable reusable component exists
  - the new component creates a durable abstraction for repeated use
  - the choice is called out in the implementation summary or plan
- In plans for UI stories, include a brief reuse note that says which existing components will be reused and where new UI surface is genuinely necessary.

### 14. Finish With Traceable Context
- When reporting back, reference:
  - the branch pack used
  - the relevant story or Jira key when applicable
  - any contract or boundary that constrained the solution
- If a task is blocked by branch ownership, schema boundaries, or Jira blockers, say so explicitly.

### 15. Respect Manual Git Publishing Ownership
- By default, do not commit, push, or open a pull request.
- The default stopping point is:
  - implementation complete
  - verification summarized
  - handoff ready
- Treat Git publishing as user-owned unless the user explicitly asks for:
  - commit creation
  - push
  - PR creation
- If the user explicitly asks an agent to create a commit, use this commit message format:
  - single Jira story: `feat(RF-??): Jira headline`
  - multiple Jira stories: `feat(RF-??, RF-??, ...): Jira headline; Jira headline; ...`
- Commit message rules:
  - use real Jira issue keys, not planning IDs embedded in summaries
  - use the current Jira headline/summary text for each included story
  - keep Jira keys and headlines in the same order
  - do not invent or abbreviate Jira headlines unless the user explicitly asks
- If a task reaches a natural delivery point, provide:
  - a concise summary of changed files
  - verification performed
  - suggested Jira comment or handoff note when relevant
  - any recommended commit or PR title, but do not execute publishing actions by default

## Do Not Do These Things
- Do not treat archived research as the current execution spec.
- Do not bypass `runtime-boundaries.md` when changing transport or data-access structure.
- Do not invent new branch ownership when a branch pack already defines it.
- Do not update `Project-Plan` just to mirror ordinary code changes.
- Do not recreate common UI primitives or write large new raw HTML blocks when reusable RecruitFlow components already exist.
- Do not assume Jira summary IDs and Jira issue keys are the same thing.
- Do not commit, push, or open PRs unless the user explicitly asks.

## Example Requests
- `Use $recruitflow-project-ops before touching RecruitFlow.`
- `Load RecruitFlow project rules, then work on the submission pipeline branch.`
- `Use $recruitflow-project-ops and continue the submission pipeline story.`

## Success Condition
- The agent can quickly determine the correct docs, correct branch pack, correct Jira context, and project-specific boundaries for this project without mixing in rules from other repos.
