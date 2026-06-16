import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

import type { CatalogSkill, SourceVerificationEntry, SourceVerificationReport, SkillctlCatalog } from "./types.js";

const execFileAsync = promisify(execFile);
const gitEnv = {
  ...process.env,
  GIT_TERMINAL_PROMPT: "0",
};
const GIT_RETRYABLE_PATTERNS = [
  /timed out/iu,
  /timeout/iu,
  /could not resolve host/iu,
  /connection reset/iu,
  /connection timed out/iu,
  /failed to connect/iu,
  /internal server error/iu,
  /http 5\d\d/iu,
  /the remote end hung up unexpectedly/iu,
];

function toText(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (Buffer.isBuffer(value)) {
    return value.toString("utf8");
  }
  return "";
}

function isRetryableGitError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error);
  if (GIT_RETRYABLE_PATTERNS.some((pattern) => pattern.test(message))) {
    return true;
  }

  if (
    error !== null &&
    typeof error === "object" &&
    "killed" in error &&
    "signal" in error &&
    error.killed === true &&
    typeof error.signal === "string" &&
    error.signal.toUpperCase() === "SIGTERM"
  ) {
    return true;
  }

  return false;
}

async function execGitWithRetry(args: string[], options: Parameters<typeof execFileAsync>[2], attempts = 2): Promise<{ stdout: string; stderr: string }> {
  let lastError: unknown;

  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      const result = await execFileAsync("git", args, options);
      return {
        stdout: toText(result.stdout),
        stderr: toText(result.stderr),
      };
    } catch (error) {
      lastError = error;
      if (attempt >= attempts || !isRetryableGitError(error)) {
        throw error;
      }
    }
  }

  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

function isUnsafeGitRevision(value: string): boolean {
  return value.trimStart().startsWith("-");
}

function isExactCommitSha(value: string): boolean {
  return /^[0-9a-f]{40}$/iu.test(value);
}

function isCommitLikeRevision(value: string): boolean {
  return /^[0-9a-f]{7,40}$/iu.test(value);
}

async function verifyPinnedCommitWithFetch(repoUrl: string, ref: string): Promise<string | null> {
  const tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "skillctl-verify-"));

  try {
    await execFileAsync("git", ["init"], {
      cwd: tempDir,
      timeout: 15000,
      env: gitEnv,
    });
    await execFileAsync("git", ["remote", "add", "origin", repoUrl], {
      cwd: tempDir,
      timeout: 15000,
      env: gitEnv,
    });
    await execGitWithRetry(["fetch", "--depth=1", "origin", ref], {
      cwd: tempDir,
      timeout: 30000,
      env: gitEnv,
    });
    const { stdout } = await execFileAsync("git", ["rev-parse", "FETCH_HEAD^{commit}"], {
      cwd: tempDir,
      timeout: 15000,
      env: gitEnv,
    });
    return stdout.trim() || null;
  } catch {
    return null;
  } finally {
    await fs.rm(tempDir, { recursive: true, force: true });
  }
}

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

  if (isUnsafeGitRevision(repo) || isUnsafeGitRevision(ref)) {
    return {
      skill_id: skill.skill_id,
      status: "error",
      detail: "upstream repo or ref begins with '-' and is rejected for git safety",
    };
  }

  try {
    const { stdout } = await execGitWithRetry(["ls-remote", "--", repoUrl, ref], {
      timeout: 15000,
      env: gitEnv,
    });
    const resolved = stdout.trim().split(/\s+/u)[0];
    if (resolved) {
      return {
        skill_id: skill.skill_id,
        status: "ok",
        detail: `verified against ${repo}`,
        resolved_ref: resolved,
      };
    }

    // ls-remote filters by ref name, so a pinned commit SHA never matches above.
    // For exact SHAs, try a shallow fetch into a temp repo to validate the commit
    // directly before falling back to more advisory outcomes.
    if (isExactCommitSha(ref)) {
      const fetched = await verifyPinnedCommitWithFetch(repoUrl, ref);
      if (fetched && fetched.toLowerCase() === ref.toLowerCase()) {
        return {
          skill_id: skill.skill_id,
          status: "ok",
          detail: `verified pinned commit ${ref} via shallow fetch from ${repo}`,
          resolved_ref: fetched,
        };
      }
    }

    if (isCommitLikeRevision(ref)) {
      const { stdout: advertised } = await execGitWithRetry(["ls-remote", "--", repoUrl], {
        timeout: 15000,
        env: gitEnv,
      });
      const needle = ref.toLowerCase();
      const match = advertised
        .split("\n")
        .map((line) => line.trim().split(/\s+/u)[0])
        .find((oid) => oid !== undefined && oid !== "" && (oid === needle || oid.startsWith(needle)));
      if (match) {
        return {
          skill_id: skill.skill_id,
          status: "ok",
          detail: `commit ${ref} is advertised by ${repo}`,
          resolved_ref: match,
        };
      }
      return {
        skill_id: skill.skill_id,
        status: "skip",
        detail: isExactCommitSha(ref)
          ? `pinned commit ${ref} could not be verified as a fetched or advertised commit on ${repo}`
          : `pinned commit ${ref} is not an advertised ref tip on ${repo}; cannot fully verify short SHA without a clone`,
      };
    }

    return {
      skill_id: skill.skill_id,
      status: "warn",
      detail: `ref not found on remote ${repo}`,
    };
  } catch (error) {
    if (isRetryableGitError(error)) {
      return {
        skill_id: skill.skill_id,
        status: "skip",
        detail: `verification skipped for ${repo}: temporary remote connectivity failure`,
      };
    }

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
