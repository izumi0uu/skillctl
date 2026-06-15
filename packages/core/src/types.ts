export type AgentId = "claude-code" | "codex" | "pi" | "hermes" | "opencode";

export type Visibility = "public" | "private";

export type SourceKind = "local-public" | "local-private" | "upstream";
export type OriginKind = "local-authored" | "imported-upstream" | "derived-from-upstream";
export type UpstreamSourceType = "github" | "git" | "local";

export type ProbePolicy = "off" | "safe";
export type TransportMode = "skills-cli" | "copy-fallback";
export type SkillPortabilityClassification = "portable" | "claude-only" | "codex-enhanced" | "needs-review";
export type SkillCategory =
  | "agent-infra"
  | "knowledge-and-research"
  | "frontend-and-design"
  | "deployment-and-platform"
  | "productivity-and-artifacts"
  | "domain-aws-thrive"
  | "system-and-demo";
export type ManagedSkillCategoryId = SkillCategory | "uncategorized";

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
    embeddedRepoPath?: string;
  };
  stateDir?: string;
}

export interface UpstreamSource {
  repo?: string;
  ref?: string;
  skillPath?: string;
  sourceType?: UpstreamSourceType;
  sourceUrl?: string;
  imported_at?: string;
  last_verified_ref?: string;
  local_modifications?: boolean;
}

export interface CatalogSkill {
  skill_id: string;
  display_name?: string;
  category?: SkillCategory;
  tags?: string[];
  visibility: Visibility;
  source_kind: SourceKind;
  origin_kind: OriginKind;
  hash: string;
  managed: boolean;
  // Absent means enabled. When false, sync removes the skill from agent dirs.
  enabled?: boolean;
  targets: AgentId[];
  canonical_rel_path?: string;
  upstream?: UpstreamSource;
  aliases?: string[];
  distribution?: {
    portability_allow_targets?: AgentId[];
  };
}

export interface SkillctlCatalog {
  version: number;
  generatedBy: string;
  skills: CatalogSkill[];
}

export interface ManagedSkillIndexEntry {
  skill_id: string;
  hash: string;
  source_hash?: string;
  rendered_hash?: string;
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

export interface SkillPortabilitySignals {
  usesStandardSkillMdOnly: boolean;
  hasClaudeDynamicContext: boolean;
  hasClaudePluginManifest: boolean;
  hasClaudePluginDirWithoutManifest: boolean;
  hasOpenAiManifest: boolean;
  hasAgentDirWithoutOpenAiManifest: boolean;
  missingName: boolean;
  missingDescription: boolean;
  targetMismatch: boolean;
}

export interface SkillPortabilityReport {
  skillId: string;
  classification: SkillPortabilityClassification;
  reasons: string[];
  canonicalRelPath: string | null;
  targets: AgentId[];
  allowedTargets: AgentId[];
  blockedTargets: AgentId[];
  overrideTargets: AgentId[];
  signals: SkillPortabilitySignals;
}

export interface RepairAction {
  type: "create-dir" | "rewrite-skill" | "remove-managed-skill" | "rewrite-index" | "rewrite-footer" | "rewrite-readme";
  agent?: AgentId;
  skillId?: string;
  detail: string;
}

export interface DoctorIssue {
  code:
    | "missing-dir"
    | "collision"
    | "unreadable-skill"
    | "drift"
    | "stale-managed-entry"
    | "invalid-config"
    | "transport-not-ready"
    | "missing-provenance"
    | "malformed-footer"
    | "footer-drift"
    | "readme-drift"
    | "catalog-mismatch"
    | "portability-review";
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
  portability: SkillPortabilityReport[];
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

export interface ResolvedTransportInvocation {
  command: string;
  args: string[];
  cwd: string;
  source: "embedded-source" | "embedded-dist" | "fallback";
  detail: string;
}

export interface TransportHealthReport {
  status: DoctorStatus;
  detail: string;
  invocation: ResolvedTransportInvocation;
}

export interface BootstrapUpstreamResult {
  embeddedRepoPath: string;
  steps: string[];
  invocation: {
    command: string[];
    source: ResolvedTransportInvocation["source"];
  };
}

export interface SourceRegistryEntry {
  skill_id: string;
  category: ManagedSkillCategoryId;
  category_label: string;
  tags: string[];
  visibility: Visibility;
  source_kind: SourceKind;
  origin_kind: OriginKind;
  managed: boolean;
  canonical_rel_path: string | null;
  upstream_repo: string | null;
  upstream_path: string | null;
  ref: string | null;
  upstream_source_type: UpstreamSourceType | null;
  upstream_source_url: string | null;
  last_verified_ref: string | null;
  local_modifications: boolean;
}

export interface ManagedSkillCategoryDefinition {
  id: ManagedSkillCategoryId;
  label: string;
  purpose: string;
}

export interface ManagedSkillTaxonomySkill {
  skill_id: string;
  display_name?: string;
  category: ManagedSkillCategoryId;
  category_label: string;
  tags: string[];
  visibility: Visibility;
  source_kind: SourceKind;
  origin_kind: OriginKind;
  managed: boolean;
  canonical_rel_path: string | null;
  targets: AgentId[];
  has_upstream: boolean;
  local_modifications: boolean;
}

export interface ManagedSkillTaxonomyGroup extends ManagedSkillCategoryDefinition {
  skillCount: number;
  skills: ManagedSkillTaxonomySkill[];
}

export interface ManagedSkillTaxonomySummaryEntry extends ManagedSkillCategoryDefinition {
  skillCount: number;
  managedSkillCount: number;
  upstreamSkillCount: number;
  localAuthoredCount: number;
}

export interface ManagedSkillTaxonomySummary {
  totalSkills: number;
  managedSkills: number;
  upstreamSkills: number;
  uncategorizedSkills: number;
  categories: ManagedSkillTaxonomySummaryEntry[];
}

export interface ManagedSkillTaxonomy {
  availableCategories: ManagedSkillCategoryDefinition[];
  categories: ManagedSkillTaxonomyGroup[];
  summary: ManagedSkillTaxonomySummary;
}

export interface SourceRegistryCategorySummary {
  id: ManagedSkillCategoryId;
  label: string;
  totalSkills: number;
  upstreamSkills: number;
  localModifiedSkills: number;
}

export interface SourceRegistrySummary {
  totalSkills: number;
  withUpstreamProvenance: number;
  missingUpstreamMetadata: number;
  localModifications: number;
  byOriginKind: Record<OriginKind, number>;
  bySourceKind: Record<SourceKind, number>;
  byCategory: SourceRegistryCategorySummary[];
}

export interface SourceVerificationEntry {
  skill_id: string;
  status: "ok" | "warn" | "error" | "skip";
  detail: string;
  resolved_ref?: string;
}

export interface SourceVerificationReport {
  ok: boolean;
  results: SourceVerificationEntry[];
  catalog: SkillctlCatalog;
}
