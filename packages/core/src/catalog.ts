import path from "node:path";

import { readJson, writeJson } from "./fs.js";
import { CATALOG_FILE } from "./paths.js";
import { skillctlCatalogSchema } from "./schema.js";
import type { AgentId, CatalogSkill, SkillDescriptor, SkillctlCatalog } from "./types.js";
import { inferSourceKind } from "./skill.js";

export function managedSkillsForAgent(catalog: SkillctlCatalog, agent: AgentId): CatalogSkill[] {
  return catalog.skills.filter((skill) => skill.managed && skill.targets.includes(agent));
}

export function emptyCatalog(): SkillctlCatalog {
  return {
    version: 1,
    generatedBy: "skillctl",
    skills: [],
  };
}

export async function loadCatalog(repoRoot: string): Promise<SkillctlCatalog> {
  const filePath = path.join(repoRoot, CATALOG_FILE);
  const raw = await readJson<unknown>(filePath);
  return skillctlCatalogSchema.parse(raw);
}

export async function writeCatalog(repoRoot: string, catalog: SkillctlCatalog): Promise<void> {
  const validated = skillctlCatalogSchema.parse(catalog);
  await writeJson(path.join(repoRoot, CATALOG_FILE), validated);
}

export function descriptorToCatalogSkill(repoRoot: string, descriptor: SkillDescriptor, targets: CatalogSkill["targets"]): CatalogSkill {
  return {
    skill_id: descriptor.skillId,
    visibility: descriptor.visibility,
    source_kind: inferSourceKind(descriptor.visibility),
    origin_kind: "local-authored",
    hash: descriptor.hash,
    managed: descriptor.managedByDefault,
    targets,
    canonical_rel_path: path.relative(repoRoot, descriptor.dirPath),
  };
}

export function mergeCatalogSkillMetadata(previous: CatalogSkill | undefined, next: CatalogSkill): CatalogSkill {
  if (!previous) {
    return next;
  }

  return {
    ...next,
    display_name: previous.display_name ?? next.display_name,
    source_kind: previous.origin_kind === "local-authored" ? next.source_kind : previous.source_kind,
    origin_kind: previous.origin_kind ?? next.origin_kind,
    managed: previous.managed,
    targets: previous.targets.length > 0 ? previous.targets : next.targets,
    upstream: previous.upstream ?? next.upstream,
    aliases: previous.aliases ?? next.aliases,
  };
}

export function summarizeCatalog(catalog: SkillctlCatalog): { managedSkills: number; publicSkills: number; privateSkills: number; upstreamSkills: number } {
  return {
    managedSkills: catalog.skills.filter((skill) => skill.managed).length,
    publicSkills: catalog.skills.filter((skill) => skill.visibility === "public").length,
    privateSkills: catalog.skills.filter((skill) => skill.visibility === "private").length,
    upstreamSkills: catalog.skills.filter((skill) => skill.origin_kind !== "local-authored").length,
  };
}
