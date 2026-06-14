import fs from "node:fs/promises";
import path from "node:path";

import { applySkillAttribution, hasMalformedAttributionBlock, readmeSourceRegistryDrift, sourceDirForSkill } from "./attribution.js";
import { getAdapter, runProbe } from "./adapters.js";
import { managedSkillsForAgent, summarizeCatalog } from "./catalog.js";
import { fileExists, readText } from "./fs.js";
import { loadManagedIndex } from "./indexes.js";
import { hashDirectory } from "./hash.js";
import { analyzeSkillPortability, evaluateSkillDistributionPolicy, portabilityBlockReason } from "./portability.js";
import { transportHealth } from "./transport.js";
import type { DoctorIssue, DoctorReport, RepairAction, SkillPortabilityReport, SkillctlCatalog, SkillctlConfig } from "./types.js";

export async function runDoctor(repoRoot: string, config: SkillctlConfig, catalog: SkillctlCatalog): Promise<DoctorReport> {
  const issues: DoctorIssue[] = [];
  const repairActions: RepairAction[] = [];
  const portability: SkillPortabilityReport[] = [];

  const transportStatus = await transportHealth(config);
  if (transportStatus.status !== "ok") {
    issues.push({
      code: transportStatus.status === "warn" ? "transport-not-ready" : "invalid-config",
      status: transportStatus.status,
      detail: transportStatus.detail,
      repairable: transportStatus.status === "warn",
    });
  }

  for (const skill of catalog.skills) {
    if (skill.origin_kind !== "local-authored") {
      if (!skill.upstream?.repo || !skill.upstream?.skillPath || !skill.upstream?.ref) {
        issues.push({
          code: "missing-provenance",
          status: "warn",
          detail: `${skill.skill_id} is missing upstream repo, path, or ref`,
          skillId: skill.skill_id,
          repairable: false,
        });
      }
    }

    const sourceDir = sourceDirForSkill(repoRoot, skill);
    if (!sourceDir) {
      continue;
    }
    const sourceSkillFile = path.join(sourceDir, "SKILL.md");
    if (!await fileExists(sourceSkillFile)) {
      continue;
    }

    const portabilityReport = await analyzeSkillPortability(sourceDir, skill);
    portability.push(portabilityReport);
    if (portabilityReport.classification === "needs-review") {
      issues.push({
        code: "portability-review",
        status: "warn",
        detail: `${skill.skill_id} portability requires review: ${portabilityReport.reasons.join("; ")}`,
        skillId: skill.skill_id,
        repairable: false,
      });
    }

    const sourceContent = await readText(sourceSkillFile);
    if (hasMalformedAttributionBlock(sourceContent)) {
      issues.push({
        code: "malformed-footer",
        status: "warn",
        detail: `${skill.skill_id} has malformed source attribution footer in canonical source`,
        skillId: skill.skill_id,
        repairable: true,
      });
      repairActions.push({ type: "rewrite-footer", agent: config.enabledAdapters[0]!, skillId: skill.skill_id, detail: `Rewrite source attribution footer for ${skill.skill_id}` });
      continue;
    }

    const expectedSource = applySkillAttribution(sourceContent, skill);
    if (expectedSource !== sourceContent) {
      issues.push({
        code: "catalog-mismatch",
        status: "warn",
        detail: `${skill.skill_id} canonical source footer does not match catalog provenance`,
        skillId: skill.skill_id,
        repairable: true,
      });
      repairActions.push({ type: "rewrite-footer", agent: config.enabledAdapters[0]!, skillId: skill.skill_id, detail: `Rewrite source attribution footer for ${skill.skill_id}` });
    }
  }

  for (const agent of config.enabledAdapters) {
    const adapter = getAdapter(agent);
    const installDir = adapter.installDir();
    const dirExists = await fileExists(installDir);
    if (!dirExists) {
      issues.push({
        code: "missing-dir",
        status: "warn",
        detail: `${agent} install dir is missing: ${installDir}`,
        agent,
        repairable: true,
      });
      repairActions.push({ type: "create-dir", agent, detail: `Create ${installDir}` });
    }

    const index = await loadManagedIndex(config.stateDir!, agent);
    const managedSkills = [];
    for (const skill of managedSkillsForAgent(catalog, agent)) {
      if (!skill.canonical_rel_path) {
        continue;
      }
      const sourceDir = path.resolve(repoRoot, skill.canonical_rel_path);
      if (!await fileExists(sourceDir)) {
        continue;
      }
      const policy = await evaluateSkillDistributionPolicy(sourceDir, skill);
      if (policy.allowedTargets.includes(agent)) {
        managedSkills.push(skill);
      }
    }

    for (const skill of managedSkills) {
      const skillDir = path.join(installDir, skill.skill_id);
      const skillFile = path.join(skillDir, "SKILL.md");
      const exists = await fileExists(skillFile);
      if (!exists) {
        issues.push({
          code: "drift",
          status: "warn",
          detail: `${agent}:${skill.skill_id} is missing or incomplete`,
          agent,
          skillId: skill.skill_id,
          repairable: true,
        });
        repairActions.push({ type: "rewrite-skill", agent, skillId: skill.skill_id, detail: `Re-copy ${skill.skill_id}` });
        continue;
      }

      try {
        const rawInstalledSkill = await readText(skillFile);
        if (hasMalformedAttributionBlock(rawInstalledSkill)) {
          issues.push({
            code: "malformed-footer",
            status: "warn",
            detail: `${agent}:${skill.skill_id} has malformed source attribution footer`,
            agent,
            skillId: skill.skill_id,
            repairable: true,
          });
          repairActions.push({ type: "rewrite-skill", agent, skillId: skill.skill_id, detail: `Re-copy ${skill.skill_id}` });
          continue;
        }

        const expectedInstalledSkill = applySkillAttribution(rawInstalledSkill, skill);
        if (expectedInstalledSkill !== rawInstalledSkill) {
          issues.push({
            code: "footer-drift",
            status: "warn",
            detail: `${agent}:${skill.skill_id} footer drift from catalog provenance`,
            agent,
            skillId: skill.skill_id,
            repairable: true,
          });
          repairActions.push({ type: "rewrite-skill", agent, skillId: skill.skill_id, detail: `Re-copy ${skill.skill_id}` });
          continue;
        }

        const installedHash = await hashDirectory(skillDir);
        if (installedHash !== skill.hash) {
          issues.push({
            code: "drift",
            status: "warn",
            detail: `${agent}:${skill.skill_id} hash drift (${installedHash} !== ${skill.hash})`,
            agent,
            skillId: skill.skill_id,
            repairable: true,
          });
          repairActions.push({ type: "rewrite-skill", agent, skillId: skill.skill_id, detail: `Re-copy ${skill.skill_id}` });
        }
      } catch (error) {
        issues.push({
          code: "unreadable-skill",
          status: "warn",
          detail: `${agent}:${skill.skill_id} unreadable: ${error instanceof Error ? error.message : String(error)}`,
          agent,
          skillId: skill.skill_id,
          repairable: true,
        });
      }
    }

    for (const entry of index.entries) {
      if (!managedSkills.some((skill) => skill.skill_id === entry.skill_id)) {
        issues.push({
          code: "stale-managed-entry",
          status: "warn",
          detail: `${agent}:${entry.skill_id} exists in managed index but not catalog`,
          agent,
          skillId: entry.skill_id,
          repairable: true,
        });
        repairActions.push({ type: "rewrite-index", agent, skillId: entry.skill_id, detail: `Rewrite ${agent} managed index` });
      }
    }

    if (dirExists) {
      const children = await fs.readdir(installDir, { withFileTypes: true });
      for (const child of children) {
        if (!child.isDirectory()) {
          continue;
        }
        const localSkillId = child.name;
        const managedMatch = managedSkills.find((skill) => skill.skill_id === localSkillId);
        if (!managedMatch) {
          continue;
        }
        const skillDir = path.join(installDir, localSkillId);
        const files = await fs.readdir(skillDir, { encoding: "utf8" }).catch((): string[] => []);
        if (!files.includes("SKILL.md")) {
          issues.push({
            code: "unreadable-skill",
            status: "warn",
            detail: `${agent}:${localSkillId} does not contain SKILL.md`,
            agent,
            skillId: localSkillId,
            repairable: true,
          });
        }
      }
    }

    for (const skill of managedSkillsForAgent(catalog, agent)) {
      if (!skill.canonical_rel_path) {
        continue;
      }
      const sourceDir = path.resolve(repoRoot, skill.canonical_rel_path);
      if (!await fileExists(sourceDir)) {
        continue;
      }
      const policy = await evaluateSkillDistributionPolicy(sourceDir, skill);
      const blockedReason = portabilityBlockReason(policy, agent);
      if (!blockedReason) {
        continue;
      }
      const blockedDir = path.join(installDir, skill.skill_id);
      if (await fileExists(blockedDir)) {
        issues.push({
          code: "drift",
          status: "warn",
          detail: `${agent}:${skill.skill_id} should not be installed (${blockedReason})`,
          agent,
          skillId: skill.skill_id,
          repairable: true,
        });
        repairActions.push({ type: "remove-managed-skill", agent, skillId: skill.skill_id, detail: `Remove blocked install of ${skill.skill_id}` });
      }
    }
  }

  if (await readmeSourceRegistryDrift(repoRoot, catalog)) {
    issues.push({
      code: "readme-drift",
      status: "warn",
      detail: "README managed skill sources section is missing or out of date",
      repairable: true,
    });
    repairActions.push({ type: "rewrite-readme", agent: config.enabledAdapters[0]!, detail: "Rewrite README managed skill sources section" });
  }

  const probes = await Promise.all(config.enabledAdapters.map((agent) => runProbe(agent, config.liveProbePolicy)));
  const hasHardError = issues.some((issue) => issue.status === "error");
  const hasWarn = issues.some((issue) => issue.status === "warn");

  return {
    healthy: !hasHardError && !hasWarn,
    exitCode: hasHardError ? 2 : hasWarn ? 1 : 0,
    issues,
    probes,
    portability,
    repairActions,
    catalogSummary: summarizeCatalog(catalog),
  };
}
