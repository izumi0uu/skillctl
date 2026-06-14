import path from "node:path";

import type {
  CatalogSkill,
  ManagedSkillCategoryDefinition,
  ManagedSkillCategoryId,
  ManagedSkillTaxonomy,
  ManagedSkillTaxonomyGroup,
  ManagedSkillTaxonomySkill,
  ManagedSkillTaxonomySummary,
  ManagedSkillTaxonomySummaryEntry,
  SkillCategory,
  SkillctlCatalog,
} from "./types.js";

const BASE_CATEGORY_DEFINITIONS: ManagedSkillCategoryDefinition[] = [
  {
    id: "agent-infra",
    label: "Agent Infra",
    purpose: "Agent runtime, configuration, recovery, and operational control-plane skills",
  },
  {
    id: "knowledge-and-research",
    label: "Knowledge And Research",
    purpose: "Knowledge workflows, learning systems, and reusable research guidance",
  },
  {
    id: "frontend-and-design",
    label: "Frontend And Design",
    purpose: "Frontend architecture, design systems, UI patterns, and motion guidance",
  },
  {
    id: "deployment-and-platform",
    label: "Deployment And Platform",
    purpose: "Deployment, cloud platform, and environment optimization workflows",
  },
  {
    id: "productivity-and-artifacts",
    label: "Productivity And Artifacts",
    purpose: "General artifact creation and productivity-oriented tool workflows",
  },
  {
    id: "domain-aws-thrive",
    label: "Domain AWS-Thrive",
    purpose: "AWS-Thrive and related domain-specific operational workflows",
  },
  {
    id: "system-and-demo",
    label: "System And Demo",
    purpose: "Portable demos, fixtures, and system validation helpers",
  },
];

export const UNCATEGORIZED_DEFINITION: ManagedSkillCategoryDefinition = {
  id: "uncategorized",
  label: "Uncategorized",
  purpose: "Skills not yet assigned to a formal category",
};

export const MANAGED_SKILL_CATEGORY_DEFINITIONS: ManagedSkillCategoryDefinition[] = [
  ...BASE_CATEGORY_DEFINITIONS,
  UNCATEGORIZED_DEFINITION,
];

const CATEGORY_DEFINITION_BY_ID = new Map(
  MANAGED_SKILL_CATEGORY_DEFINITIONS.map((definition) => [definition.id, definition]),
);

function normalizeRelPath(relPath?: string): string | undefined {
  return relPath?.split(path.sep).join("/");
}

export function inferSkillCategoryFromRelPath(relPath?: string): SkillCategory | undefined {
  const normalized = normalizeRelPath(relPath);
  if (!normalized) {
    return undefined;
  }

  const parts = normalized.split("/").filter(Boolean);
  if (parts.length < 3 || parts[0] !== "skills") {
    return undefined;
  }

  const category = parts[1];
  const definition = CATEGORY_DEFINITION_BY_ID.get(category as ManagedSkillCategoryId);
  return definition && definition.id !== "uncategorized" ? definition.id : undefined;
}

export function resolveManagedSkillCategoryId(skill: Pick<CatalogSkill, "category" | "canonical_rel_path">): ManagedSkillCategoryId {
  return skill.category ?? inferSkillCategoryFromRelPath(skill.canonical_rel_path) ?? "uncategorized";
}

export function getManagedSkillCategoryDefinition(categoryId: ManagedSkillCategoryId): ManagedSkillCategoryDefinition {
  return CATEGORY_DEFINITION_BY_ID.get(categoryId) ?? UNCATEGORIZED_DEFINITION;
}

function buildTaxonomySkill(skill: CatalogSkill): ManagedSkillTaxonomySkill {
  const category = resolveManagedSkillCategoryId(skill);
  const categoryDefinition = getManagedSkillCategoryDefinition(category);
  return {
    skill_id: skill.skill_id,
    display_name: skill.display_name,
    category,
    category_label: categoryDefinition.label,
    tags: [...(skill.tags ?? [])].sort((a, b) => a.localeCompare(b)),
    visibility: skill.visibility,
    source_kind: skill.source_kind,
    origin_kind: skill.origin_kind,
    managed: skill.managed,
    canonical_rel_path: skill.canonical_rel_path ?? null,
    targets: [...skill.targets],
    has_upstream: skill.upstream !== undefined || skill.origin_kind !== "local-authored",
    local_modifications: skill.upstream?.local_modifications ?? false,
  };
}

function buildCategorySummary(categories: ManagedSkillTaxonomyGroup[]): ManagedSkillTaxonomySummary {
  const summaryCategories: ManagedSkillTaxonomySummaryEntry[] = categories.map((group) => ({
    id: group.id,
    label: group.label,
    purpose: group.purpose,
    skillCount: group.skillCount,
    managedSkillCount: group.skills.filter((skill) => skill.managed).length,
    upstreamSkillCount: group.skills.filter((skill) => skill.origin_kind !== "local-authored").length,
    localAuthoredCount: group.skills.filter((skill) => skill.origin_kind === "local-authored").length,
  }));

  const totalSkills = summaryCategories.reduce((count, entry) => count + entry.skillCount, 0);
  const managedSkills = summaryCategories.reduce((count, entry) => count + entry.managedSkillCount, 0);
  const upstreamSkills = summaryCategories.reduce((count, entry) => count + entry.upstreamSkillCount, 0);
  const uncategorizedSkills = summaryCategories.find((entry) => entry.id === "uncategorized")?.skillCount ?? 0;

  return {
    totalSkills,
    managedSkills,
    upstreamSkills,
    uncategorizedSkills,
    categories: summaryCategories,
  };
}

export function buildManagedSkillTaxonomy(catalog: SkillctlCatalog): ManagedSkillTaxonomy {
  const grouped = new Map<ManagedSkillCategoryId, ManagedSkillTaxonomySkill[]>();

  for (const skill of [...catalog.skills].sort((a, b) => a.skill_id.localeCompare(b.skill_id))) {
    const category = resolveManagedSkillCategoryId(skill);
    const current = grouped.get(category) ?? [];
    current.push(buildTaxonomySkill(skill));
    grouped.set(category, current);
  }

  const categories: ManagedSkillTaxonomyGroup[] = [];
  for (const definition of MANAGED_SKILL_CATEGORY_DEFINITIONS) {
    const skills = grouped.get(definition.id);
    if (!skills || skills.length === 0) {
      continue;
    }
    categories.push({
      ...definition,
      skillCount: skills.length,
      skills,
    });
  }

  return {
    availableCategories: MANAGED_SKILL_CATEGORY_DEFINITIONS.map((definition) => ({ ...definition })),
    categories,
    summary: buildCategorySummary(categories),
  };
}
