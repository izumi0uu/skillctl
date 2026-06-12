export type AgentId = "claude-code" | "codex" | "pi" | "hermes" | "opencode";

export type Visibility = "public" | "private";

export type SourceKind = "local-public" | "local-private" | "upstream";

export type ProbePolicy = "off" | "safe";
export type TransportMode = "skills-cli" | "copy-fallback";

export type DoctorStatus = "ok" | "warn" | "error";

export interface SkillTargetState {
  installedHash: string | null;
  managed: boolean;
  exists: boolean;
  readable: boolean;
}

export interface SourceRoot {
  path: string;
  visibility: Visibility;
  managedByDefault?: boolean;
}

export interface SkillctlConfig {
  sourceRoots: SourceRoot[];
  privateRoots: string[];
  enabledAdapters: AgentId[];
  excludeSkills: string[];
  liveProbePolicy: ProbePolicy;
  transport: {
    mode: TransportMode;
    command: string;
    args: string[];
  };
  stateDir?: string;
}

export interface UpstreamSource {
  repo: string;
  ref: string;
  skillPath: string;
  sourceType: "github" | "git" | "local";
  sourceUrl?: string;
}

export interface CatalogSkill {
  skill_id: string;
  display_name?: string;
  visibility: Visibility;
  source_kind: SourceKind;
  hash: string;
  managed: boolean;
  targets: AgentId[];
  canonical_rel_path?: string;
  upstream?: UpstreamSource;
  aliases?: string[];
}

export interface SkillctlCatalog {
  version: number;
  generatedBy: string;
  skills: CatalogSkill[];
}

export interface ManagedSkillIndexEntry {
  skill_id: string;
  hash: string;
  managedAt: string;
}

export interface ManagedSkillIndex {
  version: number;
  agent: AgentId;
  entries: ManagedSkillIndexEntry[];
}

export interface SkillDescriptor {
  skillId: string;
  dirPath: string;
  skillFilePath: string;
  hash: string;
  visibility: Visibility;
  managedByDefault: boolean;
}

export interface SkillConflict {
  skillId: string;
  paths: string[];
}

export interface ProbeResult {
  agent: AgentId;
  status: DoctorStatus;
  detail: string;
}

export interface RepairAction {
  type: "create-dir" | "rewrite-skill" | "remove-managed-skill" | "rewrite-index";
  agent: AgentId;
  skillId?: string;
  detail: string;
}

export interface DoctorIssue {
  code: "missing-dir" | "collision" | "unreadable-skill" | "drift" | "stale-managed-entry" | "invalid-config";
  status: DoctorStatus;
  detail: string;
  agent?: AgentId;
  skillId?: string;
  repairable: boolean;
}

export interface DoctorReport {
  healthy: boolean;
  exitCode: 0 | 1 | 2;
  issues: DoctorIssue[];
  probes: ProbeResult[];
  repairActions: RepairAction[];
  catalogSummary: {
    managedSkills: number;
    publicSkills: number;
    privateSkills: number;
    upstreamSkills: number;
  };
}

export interface SyncResult {
  copied: Array<{ agent: AgentId; skillId: string }>;
  skipped: Array<{ agent: AgentId; skillId: string; reason: string }>;
  managedIndexesUpdated: AgentId[];
  transportRuns?: Array<{ agent: AgentId; command: string[] }>;
}

export interface PruneResult {
  removed: Array<{ agent: AgentId; skillId: string }>;
  skipped: Array<{ agent: AgentId; skillId: string; reason: string }>;
}
