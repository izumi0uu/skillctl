import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";

import { app, dialog } from "electron";
import { loadCatalog } from "@skillctl/core";

let currentRepoRoot: string | null = null;

async function exists(target: string): Promise<boolean> {
  return access(target).then(() => true).catch(() => false);
}

// Inlined here (rather than imported from @skillctl/core) so the desktop shell
// depends only on core's built dist, not on core source edits.
async function findWorkspaceRoot(startDir: string): Promise<string> {
  let current = startDir;
  while (true) {
    const hasWorkspace = await exists(join(current, "pnpm-workspace.yaml"));
    const hasPackage = await exists(join(current, "package.json"));
    if (hasWorkspace && hasPackage) {
      return current;
    }
    const parent = dirname(current);
    if (parent === current) {
      return startDir;
    }
    current = parent;
  }
}

function settingsPath(): string {
  return join(app.getPath("userData"), "settings.json");
}

async function readPersistedRoot(): Promise<string | null> {
  try {
    const raw = await readFile(settingsPath(), "utf8");
    return (JSON.parse(raw) as { repoRoot?: string }).repoRoot ?? null;
  } catch {
    return null;
  }
}

async function persistRoot(repoRoot: string): Promise<void> {
  await mkdir(app.getPath("userData"), { recursive: true });
  await writeFile(settingsPath(), `${JSON.stringify({ repoRoot }, null, 2)}\n`);
}

async function isSkillctlRepo(root: string): Promise<boolean> {
  return exists(join(root, "skillctl.catalog.json"));
}

export async function resolveInitialRepoRoot(): Promise<string> {
  if (currentRepoRoot) {
    return currentRepoRoot;
  }
  const persisted = await readPersistedRoot();
  if (persisted && (await isSkillctlRepo(persisted))) {
    currentRepoRoot = persisted;
    return persisted;
  }
  currentRepoRoot = await findWorkspaceRoot(app.getAppPath());
  return currentRepoRoot;
}

export function getRepoRoot(): string {
  if (!currentRepoRoot) {
    throw new Error("repo root not initialized yet");
  }
  return currentRepoRoot;
}

export async function chooseRepoRoot(): Promise<string | null> {
  const result = await dialog.showOpenDialog({
    properties: ["openDirectory"],
    title: "Select a skillctl repository",
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  const picked = await findWorkspaceRoot(result.filePaths[0]);
  if (!(await isSkillctlRepo(picked))) {
    throw new Error(`Not a skillctl repo (missing skillctl.catalog.json): ${picked}`);
  }
  // Validate the catalog parses before switching.
  await loadCatalog(picked);
  currentRepoRoot = picked;
  await persistRoot(picked);
  return picked;
}
