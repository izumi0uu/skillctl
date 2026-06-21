import path from "node:path";

import { fileExists, readJson, writeJson } from "./fs.js";
import { REPO_REFERENCES_FILE } from "./paths.js";
import { repoReferenceEntrySchema, repoReferenceRegistrySchema } from "./schema.js";
import type { RepoReferenceEntry, RepoReferenceRegistry } from "./types.js";

export function emptyRepoReferenceRegistry(): RepoReferenceRegistry {
  return {
    version: 1,
    generatedBy: "skillctl",
    references: [],
  };
}

export async function loadRepoReferenceRegistry(repoRoot: string): Promise<RepoReferenceRegistry> {
  const filePath = path.join(repoRoot, REPO_REFERENCES_FILE);
  if (!await fileExists(filePath)) {
    return emptyRepoReferenceRegistry();
  }
  const raw = await readJson<unknown>(filePath);
  return repoReferenceRegistrySchema.parse(raw);
}

export async function writeRepoReferenceRegistry(repoRoot: string, registry: RepoReferenceRegistry): Promise<void> {
  const validated = repoReferenceRegistrySchema.parse(registry);
  await writeJson(path.join(repoRoot, REPO_REFERENCES_FILE), validated);
}

export interface UpsertRepoReferenceOptions {
  replace?: boolean;
}

export function upsertRepoReference(
  registry: RepoReferenceRegistry,
  entry: RepoReferenceEntry,
  options: UpsertRepoReferenceOptions = {},
): { created: boolean; entry: RepoReferenceEntry } {
  const validated = repoReferenceEntrySchema.parse(entry);
  const existingIndex = registry.references.findIndex((reference) => reference.id === validated.id);

  if (existingIndex === -1) {
    registry.references.push(validated);
    registry.references.sort((left, right) => left.id.localeCompare(right.id));
    return { created: true, entry: validated };
  }

  if (!options.replace) {
    throw new Error(`repo reference "${validated.id}" already exists`);
  }

  registry.references[existingIndex] = validated;
  registry.references.sort((left, right) => left.id.localeCompare(right.id));
  return { created: false, entry: validated };
}
