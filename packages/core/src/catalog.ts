import path from "node:path";

import { readJson, writeJson } from "./fs.js";
import { CATALOG_FILE } from "./paths.js";
import { skillctlCatalogSchema } from "./schema.js";
import type { CatalogSkill, SkillDescriptor, SkillctlCatalog } from "./types.js";
import { inferSourceKind } from "./skill.js";

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
  await writeJson(path.join(repoRoot, CATALOG_FILE), catalog);
}

export function descriptorToCatalogSkill(repoRoot: string, descriptor: SkillDescriptor, targets: CatalogSkill["targets"]): CatalogSkill {
  return {
    skill_id: descriptor.skillId,
    visibility: descriptor.visibility,
    source_kind: inferSourceKind(descriptor.visibility),
    hash: descriptor.hash,
    managed: descriptor.managedByDefault,
    targets,
    canonical_rel_path: path.relative(repoRoot, descriptor.dirPath),
  };
}

export function summarizeCatalog(catalog: SkillctlCatalog): { managedSkills: number; publicSkills: number; privateSkills: number; upstreamSkills: number } {
  return {
    managedSkills: catalog.skills.filter((skill) => skill.managed).length,
    publicSkills: catalog.skills.filter((skill) => skill.visibility === "public").length,
    privateSkills: catalog.skills.filter((skill) => skill.visibility === "private").length,
    upstreamSkills: catalog.skills.filter((skill) => skill.source_kind === "upstream").length,
  };
}
