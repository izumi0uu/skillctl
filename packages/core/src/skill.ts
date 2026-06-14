import fs from "node:fs/promises";
import path from "node:path";
import { parse } from "yaml";

import { hashDirectory } from "./hash.js";
import { fileExists } from "./fs.js";
import type { OriginKind, SkillDescriptor, SourceKind, SourceRoot, Visibility } from "./types.js";

export async function parseSkillName(skillFilePath: string): Promise<string> {
  const raw = await fs.readFile(skillFilePath, "utf8");
  const lines = raw.split("\n");
  if (lines[0].trim() !== "---") {
    throw new Error(`SKILL.md is missing YAML frontmatter: ${skillFilePath}`);
  }

  const endIndex = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
  if (endIndex === -1) {
    throw new Error(`SKILL.md has unterminated YAML frontmatter: ${skillFilePath}`);
  }

  const frontmatter = lines.slice(1, endIndex).join("\n");
  const parsed = parse(frontmatter) as { name?: string } | null;
  if (!parsed?.name) {
    throw new Error(`SKILL.md is missing frontmatter.name: ${skillFilePath}`);
  }
  return parsed.name;
}

export async function loadSkillDescriptor(root: SourceRoot, dirPath: string): Promise<SkillDescriptor> {
  const skillFilePath = path.join(dirPath, "SKILL.md");
  if (!await fileExists(skillFilePath)) {
    throw new Error(`Missing SKILL.md in ${dirPath}`);
  }

  return {
    skillId: await parseSkillName(skillFilePath),
    dirPath,
    skillFilePath,
    hash: await hashDirectory(dirPath),
    visibility: root.visibility,
    managedByDefault: root.managedByDefault ?? true,
  };
}

export async function discoverSkillsInRoot(root: SourceRoot): Promise<SkillDescriptor[]> {
  async function visit(dirPath: string): Promise<SkillDescriptor[]> {
    const skillFilePath = path.join(dirPath, "SKILL.md");
    if (await fileExists(skillFilePath)) {
      return [await loadSkillDescriptor(root, dirPath)];
    }

    const entries = await fs.readdir(dirPath, { withFileTypes: true }).catch(() => []);
    const descriptors: SkillDescriptor[] = [];

    for (const entry of entries) {
      if (!entry.isDirectory() || entry.name.startsWith(".")) {
        continue;
      }
      descriptors.push(...await visit(path.join(dirPath, entry.name)));
    }

    return descriptors;
  }

  return visit(root.path);
}

export function inferSourceKind(visibility: Visibility, originKind: OriginKind = "local-authored"): SourceKind {
  if (originKind !== "local-authored") {
    return "upstream";
  }
  return visibility === "public" ? "local-public" : "local-private";
}
