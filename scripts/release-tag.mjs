#!/usr/bin/env node

import { execFile } from "node:child_process";
import { promisify } from "node:util";

import { isValidVersion, setWorkspaceVersion, VERSIONED_PACKAGE_FILES } from "./release-version.mjs";

const execFileAsync = promisify(execFile);

function usage() {
  console.error("Usage: node scripts/release-tag.mjs <version>");
  console.error("Example: node scripts/release-tag.mjs 0.2.0");
}

async function run(command, args) {
  await execFileAsync(command, args, { stdio: "inherit" });
}

async function capture(command, args) {
  const { stdout } = await execFileAsync(command, args, { encoding: "utf8" });
  return stdout.trim();
}

async function assertCleanWorktree() {
  const status = await capture("git", ["status", "--short"]);
  if (status) {
    throw new Error("Working tree is not clean. Commit or stash existing changes before running release:tag.");
  }
}

async function assertTagMissing(tagName) {
  try {
    await execFileAsync("git", ["rev-parse", "-q", "--verify", `refs/tags/${tagName}`]);
    throw new Error(`Tag ${tagName} already exists.`);
  } catch (error) {
    if (error.code === 0) {
      throw error;
    }
  }
}

async function main() {
  const version = process.argv[2]?.trim();
  if (!version || !isValidVersion(version)) {
    usage();
    process.exit(1);
  }

  const tagName = `v${version}`;

  await assertCleanWorktree();
  await assertTagMissing(tagName);

  await setWorkspaceVersion(version);
  await run("pnpm", ["install", "--lockfile-only"]);
  await run("pnpm", ["release:check"]);

  const commitMessage = `Prepare ${version} release

Constraint: Keep workspace package versions aligned for release automation
Rejected: Manual bump/tag choreography | Easy to desync versions and artifacts
Confidence: high
Scope-risk: narrow
Directive: Push the tag only after reviewing the generated release commit
Tested: pnpm release:check
Not-tested: GitHub Actions release workflow`;

  await run("git", ["add", ...VERSIONED_PACKAGE_FILES, "pnpm-lock.yaml"]);
  await run("git", ["commit", "-m", commitMessage]);
  await run("git", ["tag", tagName]);

  console.log(`Created release commit and local tag ${tagName}.`);
  console.log(`Next step: git push origin main --tags`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
