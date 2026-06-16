#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

export const VERSIONED_PACKAGE_FILES = [
  "package.json",
  "apps/electron/package.json",
  "packages/core/package.json",
  "packages/cli/package.json",
];

export function usage() {
  console.error("Usage: node scripts/release-version.mjs <version>");
  console.error("Example: node scripts/release-version.mjs 0.2.0");
}

export function isValidVersion(value) {
  return /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/.test(value);
}

export async function setWorkspaceVersion(nextVersion) {
  if (!nextVersion || !isValidVersion(nextVersion)) {
    throw new Error(`Invalid version: ${nextVersion ?? "<missing>"}`);
  }

  const updates = [];

  for (const relativePath of VERSIONED_PACKAGE_FILES) {
    const fullPath = resolve(relativePath);
    const original = await readFile(fullPath, "utf8");
    const json = JSON.parse(original);
    json.version = nextVersion;
    const updated = `${JSON.stringify(json, null, 2)}\n`;
    await writeFile(fullPath, updated);
    updates.push({ relativePath, original, updated });
  }

  return updates;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const nextVersion = process.argv[2]?.trim();

  if (!nextVersion || !isValidVersion(nextVersion)) {
    usage();
    process.exit(1);
  }

  const updates = await setWorkspaceVersion(nextVersion);
  for (const update of updates) {
    console.log(`updated ${update.relativePath} -> ${nextVersion}`);
  }
}
