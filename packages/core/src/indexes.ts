import { fileExists, readJson, writeJson } from "./fs.js";
import { managedIndexPath } from "./paths.js";
import { managedSkillIndexSchema } from "./schema.js";
import type { AgentId, CatalogSkill, ManagedSkillIndex } from "./types.js";

export async function loadManagedIndex(stateDir: string, agent: AgentId): Promise<ManagedSkillIndex> {
  const filePath = managedIndexPath(stateDir, agent);
  if (!await fileExists(filePath)) {
    return { version: 1, agent, entries: [] };
  }
  return managedSkillIndexSchema.parse(await readJson<unknown>(filePath));
}

export async function writeManagedIndex(stateDir: string, agent: AgentId, skills: CatalogSkill[]): Promise<void> {
  await writeJson(managedIndexPath(stateDir, agent), {
    version: 1,
    agent,
    entries: skills.filter((skill) => skill.managed && skill.targets.includes(agent)).map((skill) => ({
      skill_id: skill.skill_id,
      hash: skill.hash,
      managedAt: new Date().toISOString(),
    })),
  });
}
