import path from "node:path";

import { hashDirectory } from "./hash.js";
import { fileExists, readText, writeText } from "./fs.js";
import { README_FILE } from "./paths.js";
import {
  MANAGED_SKILL_CATEGORY_DEFINITIONS,
  buildManagedSkillTaxonomy,
  getManagedSkillCategoryDefinition,
  resolveManagedSkillCategoryId,
} from "./taxonomy.js";
import type {
  CatalogSkill,
  SkillctlCatalog,
  SourceRegistryEntry,
  SourceRegistrySummary,
  UpstreamSource,
} from "./types.js";

export const ATTRIBUTION_START = "<!-- skillctl:source-attribution:start -->";
export const ATTRIBUTION_END = "<!-- skillctl:source-attribution:end -->";
export const README_TAXONOMY_START = "<!-- skillctl:managed-skill-taxonomy:start -->";
export const README_TAXONOMY_END = "<!-- skillctl:managed-skill-taxonomy:end -->";
export const README_SOURCES_START = "<!-- skillctl:managed-skill-sources:start -->";
export const README_SOURCES_END = "<!-- skillctl:managed-skill-sources:end -->";

function hasUpstreamProvenance(skill: CatalogSkill): boolean {
  return skill.origin_kind !== "local-authored" || skill.upstream !== undefined;
}

function formatNullable(value: string | null | undefined): string {
  return value && value.trim().length > 0 ? value : "n/a";
}

function formatMarkdownLink(label: string, href: string | null | undefined): string {
  if (!href || href.trim().length === 0) {
    return label;
  }
  return `[${label}](${href})`;
}

function resolveUpstreamRepoUrl(entry: SourceRegistryEntry): string | null {
  return entry.upstream_source_url;
}

function resolveUpstreamPathUrl(entry: SourceRegistryEntry): string | null {
  if (!entry.upstream_repo || !entry.ref || !entry.upstream_path) {
    return entry.upstream_source_url;
  }

  if (/^https?:\/\//u.test(entry.upstream_repo)) {
    return entry.upstream_source_url;
  }

  if (entry.upstream_source_type === "github") {
    if (entry.upstream_path === ".") {
      return `https://github.com/${entry.upstream_repo}`;
    }
    return `https://github.com/${entry.upstream_repo}/tree/${entry.ref}/${entry.upstream_path}`;
  }

  return entry.upstream_source_url;
}

function sourceLine(label: string, value: string): string {
  return `- ${label}: ${value}`;
}

function normalizeUpstream(upstream?: UpstreamSource): Required<Pick<UpstreamSource, "repo" | "ref" | "skillPath">> & Pick<UpstreamSource, "sourceUrl" | "sourceType" | "imported_at" | "last_verified_ref" | "local_modifications"> {
  return {
    repo: upstream?.repo ?? "",
    ref: upstream?.ref ?? "",
    skillPath: upstream?.skillPath ?? "",
    sourceType: upstream?.sourceType,
    sourceUrl: upstream?.sourceUrl,
    imported_at: upstream?.imported_at,
    last_verified_ref: upstream?.last_verified_ref,
    local_modifications: upstream?.local_modifications,
  };
}

export function buildSkillAttributionBlock(skill: CatalogSkill): string {
  if (!hasUpstreamProvenance(skill)) {
    return "";
  }

  const upstream = normalizeUpstream(skill.upstream);
  const lines = [
    ATTRIBUTION_START,
    "## Source Attribution",
    "",
    sourceLine("origin kind", skill.origin_kind),
    sourceLine("upstream repo", formatNullable(upstream.repo)),
    sourceLine("upstream path", formatNullable(upstream.skillPath)),
    sourceLine("pinned ref", formatNullable(upstream.ref)),
    sourceLine("source type", formatNullable(upstream.sourceType ?? null)),
    sourceLine("source URL", formatNullable(upstream.sourceUrl ?? null)),
    sourceLine("imported at", formatNullable(upstream.imported_at ?? null)),
    sourceLine("last verified ref", formatNullable(upstream.last_verified_ref ?? null)),
    sourceLine("local modifications", String(upstream.local_modifications ?? false)),
    ATTRIBUTION_END,
  ];

  return `${lines.join("\n")}\n`;
}

export function stripSkillAttributionBlock(content: string): string {
  const start = content.indexOf(ATTRIBUTION_START);
  if (start === -1) {
    return content;
  }
  const end = content.indexOf(ATTRIBUTION_END, start);
  if (end === -1) {
    return content;
  }
  const after = end + ATTRIBUTION_END.length;
  let stripped = `${content.slice(0, start)}${content.slice(after)}`;
  stripped = stripped.replace(/\n{3,}$/u, "\n\n");
  return stripped.trimEnd() + "\n";
}

export function hasMalformedAttributionBlock(content: string): boolean {
  const hasStart = content.includes(ATTRIBUTION_START);
  const hasEnd = content.includes(ATTRIBUTION_END);
  return hasStart !== hasEnd;
}

export function applySkillAttribution(content: string, skill: CatalogSkill): string {
  const base = stripSkillAttributionBlock(content).trimEnd();
  const block = buildSkillAttributionBlock(skill);
  if (!block) {
    return `${base}\n`;
  }
  return `${base}\n\n${block}`;
}

export async function ensureSkillAttribution(skillDir: string, skill: CatalogSkill): Promise<{ changed: boolean; malformed: boolean }> {
  const skillFile = path.join(skillDir, "SKILL.md");
  const current = await readText(skillFile);
  const malformed = hasMalformedAttributionBlock(current);
  const next = applySkillAttribution(current, skill);
  if (next === current) {
    return { changed: false, malformed };
  }
  await writeText(skillFile, next);
  return { changed: true, malformed };
}

export async function expectedSkillRenderedHash(skillDir: string, skill: CatalogSkill): Promise<string> {
  await ensureSkillAttribution(skillDir, skill);
  return hashDirectory(skillDir);
}

export function sourceDirForSkill(repoRoot: string, skill: CatalogSkill): string | null {
  if (!skill.canonical_rel_path) {
    return null;
  }
  return path.resolve(repoRoot, skill.canonical_rel_path);
}

export function buildSourceRegistry(catalog: SkillctlCatalog): SourceRegistryEntry[] {
  return [...catalog.skills]
    .sort((a, b) => a.skill_id.localeCompare(b.skill_id))
    .map((skill) => {
      const category = resolveManagedSkillCategoryId(skill);
      const categoryDefinition = getManagedSkillCategoryDefinition(category);
      return {
        skill_id: skill.skill_id,
        category,
        category_label: categoryDefinition.label,
        tags: [...(skill.tags ?? [])].sort((a, b) => a.localeCompare(b)),
        visibility: skill.visibility,
        source_kind: skill.source_kind,
        origin_kind: skill.origin_kind,
        managed: skill.managed,
        canonical_rel_path: skill.canonical_rel_path ?? null,
        upstream_repo: skill.upstream?.repo ?? null,
        upstream_path: skill.upstream?.skillPath ?? null,
        ref: skill.upstream?.ref ?? null,
        upstream_source_type: skill.upstream?.sourceType ?? null,
        upstream_source_url: skill.upstream?.sourceUrl ?? null,
        last_verified_ref: skill.upstream?.last_verified_ref ?? null,
        local_modifications: skill.upstream?.local_modifications ?? false,
      };
    });
}

export function summarizeSourceRegistry(entries: SourceRegistryEntry[]): SourceRegistrySummary {
  const byOriginKind = {
    "local-authored": 0,
    "imported-upstream": 0,
    "derived-from-upstream": 0,
  } as SourceRegistrySummary["byOriginKind"];
  const bySourceKind = {
    "local-public": 0,
    "local-private": 0,
    upstream: 0,
  } as SourceRegistrySummary["bySourceKind"];

  for (const entry of entries) {
    byOriginKind[entry.origin_kind] += 1;
    bySourceKind[entry.source_kind] += 1;
  }

  const categories = MANAGED_SKILL_CATEGORY_DEFINITIONS
    .map((definition) => {
      const categoryEntries = entries.filter((entry) => entry.category === definition.id);
      if (categoryEntries.length === 0) {
        return null;
      }
      return {
        id: definition.id,
        label: definition.label,
        totalSkills: categoryEntries.length,
        upstreamSkills: categoryEntries.filter((entry) => entry.origin_kind !== "local-authored").length,
        localModifiedSkills: categoryEntries.filter((entry) => entry.local_modifications).length,
      };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry !== null);

  return {
    totalSkills: entries.length,
    withUpstreamProvenance: entries.filter((entry) => entry.origin_kind !== "local-authored" || entry.upstream_repo || entry.upstream_path || entry.ref).length,
    missingUpstreamMetadata: entries.filter((entry) => entry.origin_kind !== "local-authored" && (!entry.upstream_repo || !entry.upstream_path || !entry.ref)).length,
    localModifications: entries.filter((entry) => entry.local_modifications).length,
    byOriginKind,
    bySourceKind,
    byCategory: categories,
  };
}

export function renderManagedSkillTaxonomySection(catalog: SkillctlCatalog): string {
  const taxonomy = buildManagedSkillTaxonomy(catalog);

  const lines = [
    README_TAXONOMY_START,
    "## Managed Skill Taxonomy",
    "",
    "Canonical skill sources live under `skills/` and are grouped by usage-oriented category.",
    "",
    "| Category | Purpose | Skills |",
    "| --- | --- | --- |",
  ];

  for (const category of taxonomy.categories) {
    const renderedSkills = category.skills.map((skill) => `\`${skill.skill_id}\``).join(", ");
    lines.push(`| ${category.label} | ${category.purpose} | ${renderedSkills} |`);
  }

  lines.push(README_TAXONOMY_END);
  return `${lines.join("\n")}\n`;
}

export function injectManagedSkillTaxonomySection(readmeContent: string, catalog: SkillctlCatalog): string {
  const section = renderManagedSkillTaxonomySection(catalog).trimEnd();
  const start = readmeContent.indexOf(README_TAXONOMY_START);
  const end = readmeContent.indexOf(README_TAXONOMY_END);

  if (start !== -1 && end !== -1 && end > start) {
    const after = end + README_TAXONOMY_END.length;
    const prefix = readmeContent.slice(0, start).trimEnd();
    const suffix = readmeContent.slice(after).trimStart();
    return `${prefix}\n\n${section}\n${suffix ? `\n${suffix}` : ""}`.trimEnd() + "\n";
  }

  return `${readmeContent.trimEnd()}\n\n${section}\n`;
}

export function renderManagedSkillSourcesSection(catalog: SkillctlCatalog): string {
  const entries = buildSourceRegistry(catalog);
  const lines = [
    README_SOURCES_START,
    "## Managed Skill Sources",
    "",
    "| Skill | Category | Origin | Upstream Repo | Upstream Path | Ref | Source URL | Local Modifications |",
    "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ...entries.map((entry) => {
      const repoLabel = formatNullable(entry.upstream_repo);
      const pathLabel = formatNullable(entry.upstream_path);
      const sourceUrlLabel = entry.upstream_source_url ? "open" : "n/a";
      return `| ${entry.skill_id} | ${entry.category_label} | ${entry.origin_kind} | ${formatMarkdownLink(repoLabel, resolveUpstreamRepoUrl(entry))} | ${formatMarkdownLink(pathLabel, resolveUpstreamPathUrl(entry))} | ${formatNullable(entry.ref)} | ${formatMarkdownLink(sourceUrlLabel, entry.upstream_source_url)} | ${entry.local_modifications ? "yes" : "no"} |`;
    }),
    README_SOURCES_END,
  ];
  return `${lines.join("\n")}\n`;
}

export function injectManagedSkillSourcesSection(readmeContent: string, catalog: SkillctlCatalog): string {
  const section = renderManagedSkillSourcesSection(catalog).trimEnd();
  const start = readmeContent.indexOf(README_SOURCES_START);
  const end = readmeContent.indexOf(README_SOURCES_END);

  if (start !== -1 && end !== -1 && end > start) {
    const after = end + README_SOURCES_END.length;
    const prefix = readmeContent.slice(0, start).trimEnd();
    const suffix = readmeContent.slice(after).trimStart();
    return `${prefix}\n\n${section}\n${suffix ? `\n${suffix}` : ""}`.trimEnd() + "\n";
  }

  return `${readmeContent.trimEnd()}\n\n${section}\n`;
}

export async function ensureReadmeSourceRegistry(repoRoot: string, catalog: SkillctlCatalog): Promise<boolean> {
  const readmePath = path.join(repoRoot, README_FILE);
  if (!await fileExists(readmePath)) {
    return false;
  }
  const current = await readText(readmePath);
  const next = injectManagedSkillSourcesSection(injectManagedSkillTaxonomySection(current, catalog), catalog);
  if (next === current) {
    return false;
  }
  await writeText(readmePath, next);
  return true;
}

export async function readmeSourceRegistryDrift(repoRoot: string, catalog: SkillctlCatalog): Promise<boolean> {
  const readmePath = path.join(repoRoot, README_FILE);
  if (!await fileExists(readmePath)) {
    return true;
  }
  const current = await readText(readmePath);
  const next = injectManagedSkillSourcesSection(injectManagedSkillTaxonomySection(current, catalog), catalog);
  return current !== next;
}

export async function normalizeCatalogArtifacts(repoRoot: string, catalog: SkillctlCatalog): Promise<{ catalogChanged: boolean; readmeChanged: boolean }> {
  let catalogChanged = false;

  for (const skill of catalog.skills) {
    const skillDir = sourceDirForSkill(repoRoot, skill);
    if (!skillDir || !await fileExists(path.join(skillDir, "SKILL.md"))) {
      continue;
    }

    const result = await ensureSkillAttribution(skillDir, skill);
    const nextHash = await hashDirectory(skillDir);
    if (result.changed || nextHash !== skill.hash) {
      skill.hash = nextHash;
      catalogChanged = true;
    }
  }

  const readmeChanged = await ensureReadmeSourceRegistry(repoRoot, catalog);
  return { catalogChanged, readmeChanged };
}
