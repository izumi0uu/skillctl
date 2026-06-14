import fs from "node:fs/promises";
import type { Stats } from "node:fs";
import path from "node:path";

export const EXCLUDED_SKILL_FILES = new Set([
  "metadata.json",
  ".DS_Store",
]);

export const EXCLUDED_SKILL_DIRS = new Set([
  ".git",
  ".venv",
  "__pycache__",
  "__pypackages__",
  "node_modules",
]);

export function isExcludedSkillEntry(name: string, isDirectory = false): boolean {
  if (EXCLUDED_SKILL_FILES.has(name)) {
    return true;
  }
  if (isDirectory && EXCLUDED_SKILL_DIRS.has(name)) {
    return true;
  }
  return false;
}

async function statIfExists(filePath: string): Promise<Stats | null> {
  try {
    return await fs.stat(filePath);
  } catch {
    return null;
  }
}

export async function listPortableSkillFiles(root: string, prefix = ""): Promise<string[]> {
  const dir = path.join(root, prefix);
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files: string[] = [];

  for (const entry of entries) {
    const rel = path.join(prefix, entry.name);
    const fullPath = path.join(root, rel);

    if (entry.isDirectory()) {
      if (isExcludedSkillEntry(entry.name, true)) {
        continue;
      }
      files.push(...await listPortableSkillFiles(root, rel));
      continue;
    }

    if (entry.isSymbolicLink()) {
      const stats = await statIfExists(fullPath);
      if (!stats) {
        continue;
      }
      if (stats.isDirectory()) {
        if (isExcludedSkillEntry(entry.name, true)) {
          continue;
        }
        files.push(...await listPortableSkillFiles(root, rel));
        continue;
      }
      if (stats.isFile() && !isExcludedSkillEntry(entry.name, false)) {
        files.push(rel);
      }
      continue;
    }

    if (entry.isFile() && !isExcludedSkillEntry(entry.name, false)) {
      files.push(rel);
    }
  }

  return files.sort();
}
