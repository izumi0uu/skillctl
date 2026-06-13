import path from "node:path";

import { hashDirectory } from "./hash.js";
import { fileExists, readText, writeText } from "./fs.js";
import { README_FILE } from "./paths.js";
import type { CatalogSkill, SkillctlCatalog, SourceRegistryEntry, UpstreamSource } from "./types.js";

export const ATTRIBUTION_START = "<!-- skillctl:source-attribution:start -->";
export const ATTRIBUTION_END = "<!-- skillctl:source-attribution:end -->";
export const README_SOURCES_START = "<!-- skillctl:managed-skill-sources:start -->";
export const README_SOURCES_END = "<!-- skillctl:managed-skill-sources:end -->";

function hasUpstreamProvenance(skill: CatalogSkill): boolean {
  return skill.origin_kind !== "local-authored" || skill.upstream !== undefined;
}

function formatNullable(value: string | null | undefined): string {
  return value && value.trim().length > 0 ? value : "n/a";
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
    .map((skill) => ({
      skill_id: skill.skill_id,
      origin_kind: skill.origin_kind,
      upstream_repo: skill.upstream?.repo ?? null,
      upstream_path: skill.upstream?.skillPath ?? null,
      ref: skill.upstream?.ref ?? null,
      local_modifications: skill.upstream?.local_modifications ?? false,
    }));
}

export function renderManagedSkillSourcesSection(catalog: SkillctlCatalog): string {
  const entries = buildSourceRegistry(catalog);
  const lines = [
    README_SOURCES_START,
    "## Managed Skill Sources",
    "",
    "| Skill | Origin | Upstream Repo | Upstream Path | Ref | Local Modifications |",
    "| --- | --- | --- | --- | --- | --- |",
    ...entries.map((entry) => `| ${entry.skill_id} | ${entry.origin_kind} | ${formatNullable(entry.upstream_repo)} | ${formatNullable(entry.upstream_path)} | ${formatNullable(entry.ref)} | ${entry.local_modifications ? "yes" : "no"} |`),
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
  const next = injectManagedSkillSourcesSection(current, catalog);
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
  const next = injectManagedSkillSourcesSection(current, catalog);
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
