import path from "node:path";

import { mergeCatalogSkillMetadata } from "./catalog.js";
import { fileExists, copyDir } from "./fs.js";
import { hashDirectory } from "./hash.js";
import { inferSourceKind, parseSkillName } from "./skill.js";
import type { CatalogSkill, OriginKind, SkillctlCatalog, SkillctlConfig, UpstreamSourceType, Visibility } from "./types.js";
import { normalizeCatalogArtifacts } from "./attribution.js";

export interface AdoptSkillOptions {
  sourcePath: string;
  originKind?: OriginKind;
  visibility?: Visibility;
  sourceType?: UpstreamSourceType;
  fromRepo?: string;
  skillPath?: string;
  ref?: string;
  sourceUrl?: string;
  localModifications?: boolean;
}

export interface AdoptSkillResult {
  skill: CatalogSkill;
  destinationDir: string;
}

function inferOriginKind(options: AdoptSkillOptions): OriginKind {
  if (options.originKind) {
    return options.originKind;
  }
  if (options.fromRepo || options.ref || options.skillPath || options.sourceUrl || options.sourceType) {
    return "imported-upstream";
  }
  return "local-authored";
}

export async function adoptSkill(
  repoRoot: string,
  config: SkillctlConfig,
  catalog: SkillctlCatalog,
  options: AdoptSkillOptions,
): Promise<AdoptSkillResult> {
  const sourcePath = path.resolve(options.sourcePath);
  if (!await fileExists(path.join(sourcePath, "SKILL.md"))) {
    throw new Error(`source skill missing SKILL.md: ${sourcePath}`);
  }

  const skillId = await parseSkillName(path.join(sourcePath, "SKILL.md"));
  const destinationDir = path.join(repoRoot, "skills", skillId);
  await copyDir(sourcePath, destinationDir);

  const originKind = inferOriginKind(options);
  const visibility = options.visibility ?? "public";
  const upstream = originKind === "local-authored" && !options.fromRepo && !options.ref && !options.skillPath && !options.sourceUrl && !options.sourceType
    ? undefined
    : {
        repo: options.fromRepo,
        ref: options.ref,
        skillPath: options.skillPath,
        sourceType: options.sourceType,
        sourceUrl: options.sourceUrl,
        imported_at: new Date().toISOString(),
        last_verified_ref: options.ref,
        local_modifications: options.localModifications ?? originKind === "derived-from-upstream",
      };

  const discovered: CatalogSkill = {
    skill_id: skillId,
    visibility,
    source_kind: inferSourceKind(visibility),
    origin_kind: originKind,
    hash: await hashDirectory(destinationDir),
    managed: true,
    targets: config.enabledAdapters,
    canonical_rel_path: path.relative(repoRoot, destinationDir),
    upstream,
  };

  const previous = catalog.skills.find((skill) => skill.skill_id === skillId);
  const merged = mergeCatalogSkillMetadata(previous, discovered);
  const nextSkills = catalog.skills.filter((skill) => skill.skill_id !== skillId);
  nextSkills.push(merged);
  nextSkills.sort((a, b) => a.skill_id.localeCompare(b.skill_id));
  catalog.skills = nextSkills;
  await normalizeCatalogArtifacts(repoRoot, catalog);

  const adopted = catalog.skills.find((skill) => skill.skill_id === skillId);
  if (!adopted) {
    throw new Error(`failed to adopt ${skillId}`);
  }

  return {
    skill: adopted,
    destinationDir,
  };
}
