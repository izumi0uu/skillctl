import path from "node:path";
import os from "node:os";

import type { AgentId } from "./types.js";

export const CONFIG_FILE = "skillctl.config.json";
export const CATALOG_FILE = "skillctl.catalog.json";
export const DEFAULT_EMBEDDED_SKILLS_REPO = "vercel-skills";

export function defaultStateDir(repoRoot: string): string {
  return path.join(repoRoot, ".skillctl-local");
}

export function expandHome(inputPath: string): string {
  if (inputPath === "~") {
    return os.homedir();
  }
  if (inputPath.startsWith("~/")) {
    return path.join(os.homedir(), inputPath.slice(2));
  }
  return inputPath;
}

export function managedIndexPath(stateDir: string, agent: AgentId): string {
  return path.join(stateDir, "managed", `${agent}.json`);
}
