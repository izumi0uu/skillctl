import { syncCatalog } from "./sync.js";
import { runDoctor } from "./doctor.js";
import type { DoctorReport, SkillctlCatalog, SkillctlConfig } from "./types.js";
import type { SyncProgressCallback } from "./transport.js";

export async function repairCatalog(
  repoRoot: string,
  config: SkillctlConfig,
  catalog: SkillctlCatalog,
  onProgress?: SyncProgressCallback,
): Promise<DoctorReport> {
  await syncCatalog(repoRoot, config, catalog, onProgress);
  return runDoctor(repoRoot, config, catalog);
}
