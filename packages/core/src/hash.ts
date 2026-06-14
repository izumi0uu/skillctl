import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";

import { listPortableSkillFiles } from "./portable-skill-files.js";

export async function hashDirectory(dirPath: string): Promise<string> {
  const hash = crypto.createHash("sha1");
  const files = await listPortableSkillFiles(dirPath);

  for (const rel of files) {
    hash.update(rel);
    hash.update("\n");
    hash.update(await fs.readFile(path.join(dirPath, rel)));
    hash.update("\n");
  }

  return hash.digest("hex");
}
