import path from "node:path";
import { parse } from "yaml";

import { readText } from "./fs.js";
import { listPortableSkillFiles } from "./portable-skill-files.js";
import type {
  AgentId,
  CatalogSkill,
  SkillPortabilityClassification,
  SkillPortabilityReport,
  SkillPortabilitySignals,
} from "./types.js";

interface ParsedFrontmatter {
  name?: unknown;
  description?: unknown;
}

export interface SkillDistributionPolicy {
  skill: CatalogSkill;
  classification: SkillPortabilityClassification;
  allowedTargets: AgentId[];
  blockedTargets: Array<{ agent: AgentId; reason: string }>;
  overrideTargets: AgentId[];
  reasons: string[];
  signals: SkillPortabilitySignals;
}

function uniqueAgents(agents: AgentId[]): AgentId[] {
  return [...new Set(agents)];
}

async function parseSkillFrontmatter(skillFilePath: string): Promise<ParsedFrontmatter | null> {
  const raw = await readText(skillFilePath);
  const lines = raw.split("\n");
  if (lines[0]?.trim() !== "---") {
    return null;
  }

  const endIndex = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  if (endIndex === -1) {
    return null;
  }

  const frontmatter = lines.slice(1, endIndex).join("\n");
  return (parse(frontmatter) as ParsedFrontmatter | null) ?? null;
}

function includesClaudeDynamicContext(rawSkill: string): boolean {
  const lines = rawSkill.split("\n");
  let inFencedCodeBlock = false;

  for (const line of lines) {
    const trimmed = line.trimStart();
    if (/^(```|~~~)/u.test(trimmed)) {
      inFencedCodeBlock = !inFencedCodeBlock;
      continue;
    }
    if (inFencedCodeBlock) {
      continue;
    }
    if (/^![`<]/u.test(trimmed)) {
      return true;
    }
  }

  return false;
}

function buildSignals(): SkillPortabilitySignals {
  return {
    usesStandardSkillMdOnly: true,
    hasClaudeDynamicContext: false,
    hasClaudePluginManifest: false,
    hasClaudePluginDirWithoutManifest: false,
    hasOpenAiManifest: false,
    hasAgentDirWithoutOpenAiManifest: false,
    missingName: false,
    missingDescription: false,
    targetMismatch: false,
  };
}

function classifySignals(signals: SkillPortabilitySignals): SkillPortabilityClassification {
  if (
    signals.missingName ||
    signals.missingDescription ||
    signals.hasClaudePluginDirWithoutManifest ||
    signals.hasAgentDirWithoutOpenAiManifest
  ) {
    return "needs-review";
  }

  if (signals.hasClaudeDynamicContext || signals.hasClaudePluginManifest) {
    return "claude-only";
  }

  if (signals.hasOpenAiManifest) {
    return "codex-enhanced";
  }

  return "portable";
}

function buildReasons(signals: SkillPortabilitySignals): string[] {
  const reasons: string[] = [];

  if (signals.usesStandardSkillMdOnly) {
    reasons.push("uses portable SKILL.md structure without host-specific extensions");
  }
  if (signals.hasClaudeDynamicContext) {
    reasons.push("uses Claude dynamic context injection syntax in SKILL.md");
  }
  if (signals.hasClaudePluginManifest) {
    reasons.push("contains .claude-plugin manifest");
  }
  if (signals.hasClaudePluginDirWithoutManifest) {
    reasons.push("contains .claude-plugin directory without manifest file");
  }
  if (signals.hasOpenAiManifest) {
    reasons.push("contains agents/openai.yaml for OpenAI or Codex-specific metadata");
  }
  if (signals.hasAgentDirWithoutOpenAiManifest) {
    reasons.push("contains agents/ directory without agents/openai.yaml");
  }
  if (signals.missingName) {
    reasons.push("missing frontmatter.name in SKILL.md");
  }
  if (signals.missingDescription) {
    reasons.push("missing frontmatter.description in SKILL.md");
  }
  if (signals.targetMismatch) {
    reasons.push("declared targets differ from portability expectations");
  }

  return reasons;
}

function evaluateAllowedTargets(skill: CatalogSkill, classification: SkillPortabilityClassification): {
  allowedTargets: AgentId[];
  blockedTargets: Array<{ agent: AgentId; reason: string }>;
  overrideTargets: AgentId[];
} {
  const declaredTargets = uniqueAgents(skill.targets);
  const rawOverrides = uniqueAgents(skill.distribution?.portability_allow_targets ?? []);
  const overrideTargets = rawOverrides.filter((agent) => declaredTargets.includes(agent));
  const allowed = new Set<AgentId>();
  const blockedTargets: Array<{ agent: AgentId; reason: string }> = [];

  for (const agent of declaredTargets) {
    let allowedByDefault = false;
    let reason = "";

    switch (classification) {
      case "portable":
      case "codex-enhanced":
        allowedByDefault = true;
        break;
      case "claude-only":
        allowedByDefault = agent === "claude-code";
        reason = "blocked by claude-only portability policy";
        break;
      case "needs-review":
        allowedByDefault = false;
        reason = "blocked by needs-review portability policy";
        break;
    }

    if (allowedByDefault) {
      allowed.add(agent);
      continue;
    }

    const hasOverride = overrideTargets.includes(agent);
    if (hasOverride && classification !== "needs-review") {
      allowed.add(agent);
      continue;
    }

    blockedTargets.push({ agent, reason });
  }

  return {
    allowedTargets: [...allowed],
    blockedTargets,
    overrideTargets,
  };
}

export async function analyzeSkillPortability(skillDir: string, skill: CatalogSkill): Promise<SkillPortabilityReport> {
  const skillFilePath = path.join(skillDir, "SKILL.md");
  const files = await listPortableSkillFiles(skillDir);
  const rawSkill = await readText(skillFilePath);
  const frontmatter = await parseSkillFrontmatter(skillFilePath);
  const signals = buildSignals();

  const hasClaudePluginDir = files.some((file) => file.startsWith(".claude-plugin/"));
  const hasClaudePluginManifest = files.includes(".claude-plugin/manifest.json");
  const hasOpenAiManifest = files.includes("agents/openai.yaml");
  const hasAgentDir = files.some((file) => file.startsWith("agents/"));

  signals.hasClaudeDynamicContext = includesClaudeDynamicContext(rawSkill);
  signals.hasClaudePluginManifest = hasClaudePluginManifest;
  signals.hasClaudePluginDirWithoutManifest = hasClaudePluginDir && !hasClaudePluginManifest;
  signals.hasOpenAiManifest = hasOpenAiManifest;
  signals.hasAgentDirWithoutOpenAiManifest = hasAgentDir && !hasOpenAiManifest;
  signals.missingName = !frontmatter || typeof frontmatter.name !== "string" || frontmatter.name.trim().length === 0;
  signals.missingDescription = !frontmatter || typeof frontmatter.description !== "string" || frontmatter.description.trim().length === 0;

  signals.usesStandardSkillMdOnly = !signals.hasClaudeDynamicContext
    && !signals.hasClaudePluginManifest
    && !signals.hasClaudePluginDirWithoutManifest
    && !signals.hasOpenAiManifest
    && !signals.hasAgentDirWithoutOpenAiManifest;

  const classification = classifySignals(signals);
  const expectsClaude = signals.hasClaudeDynamicContext || signals.hasClaudePluginManifest || signals.hasClaudePluginDirWithoutManifest;
  const expectsCodex = signals.hasOpenAiManifest || signals.hasAgentDirWithoutOpenAiManifest;
  signals.targetMismatch = (expectsClaude && !skill.targets.includes("claude-code"))
    || (expectsCodex && !skill.targets.includes("codex"));

  const policy = evaluateAllowedTargets(skill, classification);
  return {
    skillId: skill.skill_id,
    classification,
    reasons: buildReasons(signals),
    canonicalRelPath: skill.canonical_rel_path ?? null,
    targets: [...skill.targets],
    allowedTargets: policy.allowedTargets,
    blockedTargets: policy.blockedTargets.map((entry) => entry.agent),
    overrideTargets: policy.overrideTargets,
    signals,
  };
}

export async function evaluateSkillDistributionPolicy(skillDir: string, skill: CatalogSkill): Promise<SkillDistributionPolicy> {
  const report = await analyzeSkillPortability(skillDir, skill);
  const blockedTargets = report.blockedTargets.map((agent) => ({
    agent,
    reason: report.classification === "needs-review"
      ? "blocked by needs-review portability policy"
      : "blocked by claude-only portability policy",
  }));

  return {
    skill,
    classification: report.classification,
    allowedTargets: report.allowedTargets,
    blockedTargets,
    overrideTargets: report.overrideTargets,
    reasons: report.reasons,
    signals: report.signals,
  };
}

export function portabilityBlockReason(policy: SkillDistributionPolicy, agent: AgentId): string | null {
  return policy.blockedTargets.find((entry) => entry.agent === agent)?.reason ?? null;
}
