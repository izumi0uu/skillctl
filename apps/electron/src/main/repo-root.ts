import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";

import { app, dialog } from "electron";
import { loadCatalog } from "@skillctl/core";

let currentRepoRoot: string | null = null;

async function exists(target: string): Promise<boolean> {
  return access(target).then(() => true).catch(() => false);
}

async function findMonorepoRoot(startDir: string): Promise<string> {
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

async function findNearestSkillctlRoot(startDir: string): Promise<string | null> {
  let current = startDir;
  while (true) {
    if (await isSkillctlRepo(current)) {
      return current;
    }
    const parent = dirname(current);
    if (parent === current) {
      return null;
    }
    current = parent;
  }
}

async function pickWorkspaceFolder(): Promise<string | null> {
  const result = await dialog.showOpenDialog({
    properties: ["openDirectory"],
    title: "Select a skillctl workspace folder",
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  const selected = result.filePaths[0];
  return (await findNearestSkillctlRoot(selected)) ?? selected;
}

function defaultPackagedWorkspace(): string {
  return join(app.getPath("documents"), "skillctl-workspace");
}

export const __repoRootInternals = {
  findMonorepoRoot,
  defaultPackagedWorkspace,
  resetForTests() {
    currentRepoRoot = null;
  },
};

export async function resolveInitialRepoRoot(): Promise<string> {
  if (currentRepoRoot) {
    return currentRepoRoot;
  }

  if (!app.isPackaged) {
    currentRepoRoot = await findMonorepoRoot(app.getAppPath());
    return currentRepoRoot;
  }

  const persisted = await readPersistedRoot();
  if (persisted) {
    currentRepoRoot = persisted;
    return persisted;
  }

  currentRepoRoot = defaultPackagedWorkspace();
  await persistRoot(currentRepoRoot);
  return currentRepoRoot;
}

export function getRepoRoot(): string {
  if (!currentRepoRoot) {
    throw new Error("repo root not initialized yet");
  }
  return currentRepoRoot;
}

export async function chooseRepoRoot(): Promise<string | null> {
  const picked = await pickWorkspaceFolder();
  if (!picked) {
    return null;
  }

  currentRepoRoot = picked;
  await persistRoot(picked);

  if (await isSkillctlRepo(picked)) {
    await loadCatalog(picked);
  }

  return picked;
}
