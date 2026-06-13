import { execFile } from "node:child_process";
import { promisify } from "node:util";

import type { CatalogSkill, SourceVerificationEntry, SourceVerificationReport, SkillctlCatalog } from "./types.js";

const execFileAsync = promisify(execFile);

function verifySkillSourceInput(skill: CatalogSkill): SourceVerificationEntry | null {
  if (skill.origin_kind === "local-authored") {
    return {
      skill_id: skill.skill_id,
      status: "skip",
      detail: "local-authored skill does not require upstream verification",
    };
  }

  if (!skill.upstream?.repo || !skill.upstream?.skillPath || !skill.upstream?.ref) {
    return {
      skill_id: skill.skill_id,
      status: "warn",
      detail: "missing repo, skill path, or ref in upstream provenance",
    };
  }

  return null;
}

async function verifyGithubRef(skill: CatalogSkill): Promise<SourceVerificationEntry> {
  const upstream = skill.upstream!;
  const repo = upstream.repo!;
  const ref = upstream.ref!;
  const repoUrl = repo.startsWith("http://") || repo.startsWith("https://") ? repo : `https://github.com/${repo}.git`;

  try {
    const { stdout } = await execFileAsync("git", ["ls-remote", repoUrl, ref], {
      timeout: 15000,
      env: process.env,
    });
    const resolved = stdout.trim().split(/\s+/u)[0];
    if (!resolved) {
      return {
        skill_id: skill.skill_id,
        status: "warn",
        detail: `ref not found on remote ${repo}`,
      };
    }
    return {
      skill_id: skill.skill_id,
      status: "ok",
      detail: `verified against ${repo}`,
      resolved_ref: resolved,
    };
  } catch (error) {
    return {
      skill_id: skill.skill_id,
      status: "error",
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

async function verifyLocalRef(skill: CatalogSkill): Promise<SourceVerificationEntry> {
  const upstream = skill.upstream!;
  return {
    skill_id: skill.skill_id,
    status: "skip",
    detail: `local source ${upstream.repo ?? "unknown"} not probed automatically`,
  };
}

export async function verifyCatalogSources(catalog: SkillctlCatalog): Promise<SourceVerificationReport> {
  const results: SourceVerificationEntry[] = [];

  for (const skill of [...catalog.skills].sort((a, b) => a.skill_id.localeCompare(b.skill_id))) {
    const preflight = verifySkillSourceInput(skill);
    if (preflight) {
      results.push(preflight);
      continue;
    }

    if (skill.upstream?.sourceType === "local") {
      results.push(await verifyLocalRef(skill));
      continue;
    }

    results.push(await verifyGithubRef(skill));
  }

  return {
    ok: results.every((result) => result.status === "ok" || result.status === "skip"),
    results,
    catalog,
  };
}
