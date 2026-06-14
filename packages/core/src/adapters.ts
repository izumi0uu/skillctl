import path from "node:path";
import os from "node:os";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

import type { AgentId, ProbePolicy, ProbeResult } from "./types.js";

const execFileAsync = promisify(execFile);

export interface AgentAdapter {
  id: AgentId;
  label: string;
  installDir(homeDir?: string): string;
  canProbe: boolean;
  skillsCliAgent?: string;
  probeCommand?: { file: string; args: string[] };
}

const home = () => os.homedir();

export const BUILTIN_ADAPTERS: Record<AgentId, AgentAdapter> = {
  "claude-code": {
    id: "claude-code",
    label: "Claude Code",
    installDir: (homeDir = home()) => path.join(homeDir, ".claude", "skills"),
    canProbe: true,
    skillsCliAgent: "claude-code",
    probeCommand: { file: "claude", args: ["--help"] },
  },
  codex: {
    id: "codex",
    label: "Codex",
    installDir: (homeDir = home()) => path.join(homeDir, ".codex", "skills"),
    canProbe: true,
    skillsCliAgent: "codex",
    probeCommand: { file: "codex", args: ["--help"] },
  },
  pi: {
    id: "pi",
    label: "Pi Agent",
    installDir: (homeDir = home()) => path.join(homeDir, ".pi", "agent", "skills"),
    canProbe: false,
    skillsCliAgent: "pi",
  },
  hermes: {
    id: "hermes",
    label: "Hermes",
    installDir: (homeDir = home()) => path.join(homeDir, ".hermes", "skills"),
    canProbe: true,
    skillsCliAgent: "hermes-agent",
    probeCommand: { file: "hermes", args: ["--help"] },
  },
  opencode: {
    id: "opencode",
    label: "OpenCode",
    installDir: (homeDir = home()) => path.join(homeDir, ".config", "opencode", "skills"),
    canProbe: true,
    skillsCliAgent: "opencode",
    probeCommand: { file: "opencode", args: ["--help"] },
  },
};

export function getAdapter(agent: AgentId): AgentAdapter {
  return BUILTIN_ADAPTERS[agent];
}

export function listAdapters(): AgentAdapter[] {
  return Object.values(BUILTIN_ADAPTERS);
}

export async function runProbe(agent: AgentId, policy: ProbePolicy): Promise<ProbeResult> {
  const adapter = getAdapter(agent);
  if (policy === "off") {
    return { agent, status: "ok", detail: "live probe disabled" };
  }
  if (!adapter.canProbe || !adapter.probeCommand) {
    return { agent, status: "warn", detail: "live probe unavailable for this adapter" };
  }

  try {
    await execFileAsync(adapter.probeCommand.file, adapter.probeCommand.args, { timeout: 5000 });
    return { agent, status: "ok", detail: `${adapter.probeCommand.file} probe passed` };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    return { agent, status: "warn", detail: `${adapter.probeCommand.file} probe failed: ${detail}` };
  }
}
