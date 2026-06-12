import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

async function listFiles(root: string, prefix = ""): Promise<string[]> {
  const dir = path.join(root, prefix);
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files: string[] = [];

  for (const entry of entries) {
    if (entry.name === ".DS_Store" || entry.name === ".git") {
      continue;
    }
    const rel = path.join(prefix, entry.name);
    if (entry.isDirectory()) {
      files.push(...await listFiles(root, rel));
      continue;
    }
    if (entry.isFile()) {
      files.push(rel);
    }
  }

  return files.sort();
}

export async function hashDirectory(dirPath: string): Promise<string> {
  const hash = crypto.createHash("sha1");
  const files = await listFiles(dirPath);

  for (const rel of files) {
    hash.update(rel);
    hash.update("\n");
    hash.update(await fs.readFile(path.join(dirPath, rel)));
    hash.update("\n");
  }

  return hash.digest("hex");
}
