import { syncCatalog } from "./sync.js";
import { runDoctor } from "./doctor.js";
import type { DoctorReport, SkillctlCatalog, SkillctlConfig } from "./types.js";

export async function repairCatalog(repoRoot: string, config: SkillctlConfig, catalog: SkillctlCatalog): Promise<DoctorReport> {
  await syncCatalog(repoRoot, config, catalog);
  return runDoctor(repoRoot, config, catalog);
}
