import fs from "node:fs/promises";
import path from "node:path";

import { getAdapter, runProbe } from "./adapters.js";
import { summarizeCatalog } from "./catalog.js";
import { fileExists } from "./fs.js";
import { loadManagedIndex } from "./indexes.js";
import { hashDirectory } from "./hash.js";
import type { CatalogSkill, DoctorIssue, DoctorReport, RepairAction, SkillctlCatalog, SkillctlConfig } from "./types.js";

function managedSkillsForAgent(catalog: SkillctlCatalog, agent: CatalogSkill["targets"][number]): CatalogSkill[] {
  return catalog.skills.filter((skill) => skill.managed && skill.targets.includes(agent));
}

export async function runDoctor(repoRoot: string, config: SkillctlConfig, catalog: SkillctlCatalog): Promise<DoctorReport> {
  const issues: DoctorIssue[] = [];
  const repairActions: RepairAction[] = [];

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
    const managedSkills = managedSkillsForAgent(catalog, agent);

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
  }

  const probes = await Promise.all(config.enabledAdapters.map((agent) => runProbe(agent, config.liveProbePolicy)));
  const hasHardError = issues.some((issue) => issue.status === "error");
  const hasWarn = issues.some((issue) => issue.status === "warn");

  return {
    healthy: !hasHardError && !hasWarn,
    exitCode: hasHardError ? 2 : hasWarn ? 1 : 0,
    issues,
    probes,
    repairActions,
    catalogSummary: summarizeCatalog(catalog),
  };
}
