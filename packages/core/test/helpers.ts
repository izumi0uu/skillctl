import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export async function makeTempDir(prefix: string): Promise<string> {
  return fs.mkdtemp(path.join(os.tmpdir(), prefix));
}

export async function writeSkill(dirPath: string, skillId: string, extraBody = ""): Promise<string> {
  const skillDir = path.join(dirPath, skillId);
  await fs.mkdir(skillDir, { recursive: true });
  await fs.writeFile(path.join(skillDir, "SKILL.md"), `---\nname: ${skillId}\ndescription: test skill ${skillId}\n---\n\n# ${skillId}\n\n${extraBody}\n`, "utf8");
  return skillDir;
}
