import fs from "node:fs/promises";
import path from "node:path";

import { isExcludedSkillEntry } from "./portable-skill-files.js";

export async function fileExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

export async function ensureDir(dirPath: string): Promise<void> {
  await fs.mkdir(dirPath, { recursive: true });
}

export async function readJson<T>(filePath: string): Promise<T> {
  const raw = await fs.readFile(filePath, "utf8");
  return JSON.parse(raw) as T;
}

export async function readText(filePath: string): Promise<string> {
  return fs.readFile(filePath, "utf8");
}

export async function writeJson(filePath: string, data: unknown): Promise<void> {
  await ensureDir(path.dirname(filePath));
  await fs.writeFile(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

export async function writeText(filePath: string, content: string): Promise<void> {
  await ensureDir(path.dirname(filePath));
  await fs.writeFile(filePath, content, "utf8");
}

export async function removeDirContents(dirPath: string): Promise<void> {
  await ensureDir(dirPath);
  const entries = await fs.readdir(dirPath);
  await Promise.all(entries.map(async (entry) => fs.rm(path.join(dirPath, entry), { recursive: true, force: true })));
}

async function copySkillTree(src: string, dst: string): Promise<void> {
  await ensureDir(dst);
  const entries = await fs.readdir(src, { withFileTypes: true });

  await Promise.all(entries.map(async (entry) => {
    const srcPath = path.join(src, entry.name);
    const dstPath = path.join(dst, entry.name);

    if (entry.isDirectory()) {
      if (isExcludedSkillEntry(entry.name, true)) {
        return;
      }
      await copySkillTree(srcPath, dstPath);
      return;
    }

    if (entry.isSymbolicLink()) {
      try {
        const stats = await fs.stat(srcPath);
        if (stats.isDirectory()) {
          if (isExcludedSkillEntry(entry.name, true)) {
            return;
          }
          await copySkillTree(srcPath, dstPath);
          return;
        }
        if (stats.isFile()) {
          if (isExcludedSkillEntry(entry.name, false)) {
            return;
          }
          await fs.cp(srcPath, dstPath, { dereference: true });
        }
      } catch (error) {
        if (error && typeof error === "object" && "code" in error && error.code === "ENOENT") {
          return;
        }
        throw error;
      }
      return;
    }

    if (entry.isFile()) {
      if (isExcludedSkillEntry(entry.name, false)) {
        return;
      }
      await fs.cp(srcPath, dstPath, { dereference: true });
    }
  }));
}

export async function copyDir(src: string, dst: string): Promise<void> {
  await fs.rm(dst, { recursive: true, force: true });
  await copySkillTree(src, dst);
}
