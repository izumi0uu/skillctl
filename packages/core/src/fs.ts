import fs from "node:fs/promises";
import path from "node:path";

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

export async function writeJson(filePath: string, data: unknown): Promise<void> {
  await ensureDir(path.dirname(filePath));
  await fs.writeFile(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
}

export async function removeDirContents(dirPath: string): Promise<void> {
  await ensureDir(dirPath);
  const entries = await fs.readdir(dirPath);
  await Promise.all(entries.map(async (entry) => fs.rm(path.join(dirPath, entry), { recursive: true, force: true })));
}

export async function copyDir(src: string, dst: string): Promise<void> {
  await fs.rm(dst, { recursive: true, force: true });
  await fs.cp(src, dst, { recursive: true });
}
