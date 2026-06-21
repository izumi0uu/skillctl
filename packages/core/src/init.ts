import path from "node:path";

import { fileExists, writeJson, ensureDir } from "./fs.js";
import { writeDefaultConfig } from "./config.js";
import { CATALOG_FILE, CONFIG_FILE, REPO_REFERENCES_FILE, defaultStateDir } from "./paths.js";
import { emptyCatalog } from "./catalog.js";
import { emptyRepoReferenceRegistry } from "./repo-references.js";

export async function initRepo(repoRoot: string): Promise<{ created: string[]; skipped: string[] }> {
  const created: string[] = [];
  const skipped: string[] = [];
  const configPath = path.join(repoRoot, CONFIG_FILE);
  const catalogPath = path.join(repoRoot, CATALOG_FILE);
  const repoReferencesPath = path.join(repoRoot, REPO_REFERENCES_FILE);
  const stateDir = defaultStateDir(repoRoot);

  if (!await fileExists(configPath)) {
    await writeDefaultConfig(repoRoot);
    created.push(CONFIG_FILE);
  } else {
    skipped.push(CONFIG_FILE);
  }

  if (!await fileExists(catalogPath)) {
    await writeJson(catalogPath, emptyCatalog());
    created.push(CATALOG_FILE);
  } else {
    skipped.push(CATALOG_FILE);
  }

  if (!await fileExists(repoReferencesPath)) {
    await writeJson(repoReferencesPath, emptyRepoReferenceRegistry());
    created.push(REPO_REFERENCES_FILE);
  } else {
    skipped.push(REPO_REFERENCES_FILE);
  }

  const dirEntries = [
    { rel: "skills", abs: path.join(repoRoot, "skills") },
    { rel: "manifests", abs: path.join(repoRoot, "manifests") },
    { rel: ".skillctl-local/managed", abs: path.join(stateDir, "managed") },
  ];

  for (const entry of dirEntries) {
    if (!await fileExists(entry.abs)) {
      await ensureDir(entry.abs);
      created.push(`${entry.rel}/`);
    } else {
      skipped.push(`${entry.rel}/`);
    }
  }

  return { created, skipped };
}
