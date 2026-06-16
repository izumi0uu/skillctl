import type {
  AdoptSkillOptions,
  AdoptSkillResult,
  AgentId,
  BootstrapUpstreamResult,
  DoctorReport,
  ManagedSkillTaxonomy,
  OriginKind,
  ProbePolicy,
  PruneResult,
  SkillMetaPatch,
  SkillctlConfig,
  SkillctlCatalog,
  SourceRegistryEntry,
  SourceRegistrySummary,
  SourceVerificationReport,
  SyncResult,
} from "@skillctl/core";

export const CHANNELS = {
  repoRoot: "repo:root",
  chooseRepo: "repo:choose",
  chooseDirectory: "dialog:choose-dir",
  adopt: "adopt:run",
  readSkillDoc: "skill:read-doc",
  setSkillEnabled: "skill:set-enabled",
  openPath: "shell:open-path",
  openExternal: "shell:open-external",
  loadConfig: "config:load",
  updateConfig: "config:update",
  loadCatalog: "catalog:load",
  summary: "catalog:summary",
  taxonomy: "taxonomy:get",
  sources: "sources:get",
  doctor: "doctor:run",
  adapters: "adapters:list",
  diff: "diff:get",
  verifySources: "verify-sources:run",
  discover: "discover:run",
  sync: "sync:run",
  repair: "repair:run",
  prune: "prune:run",
  bootstrap: "bootstrap:run",
  init: "repo:init",
  repoStatus: "repo:status",
  setSkillMeta: "skill:set-meta",
  publish: "publish:get",
  skillInstalls: "skill:installs",
  progress: "op:progress",
} as const;

export type IpcResult<T> = { ok: true; data: T } | { ok: false; error: string };

export interface CatalogSummary {
  managedSkills: number;
  publicSkills: number;
  privateSkills: number;
  upstreamSkills: number;
}

export interface AdapterInfo {
  id: AgentId;
  label: string;
  installDir: string;
  canProbe: boolean;
}

export interface SourcesPayload {
  summary: SourceRegistrySummary;
  sources: SourceRegistryEntry[];
}

export type DiffKind = "added" | "removed" | "changed";
export interface DiffChange {
  skill: string;
  kind: DiffKind;
}
export interface SkillConflictLite {
  skillId: string;
  paths: string[];
}
export interface DiffPayload {
  changes: DiffChange[];
  conflicts: SkillConflictLite[];
}

export interface DiscoverResult {
  conflicts: SkillConflictLite[];
  skills: number;
}

export type ProgressPhase = "started" | "finished" | "error" | "step";
export interface ProgressEvent {
  op: string;
  phase: ProgressPhase;
  detail?: string;
  stage?: string;
  current?: number;
  total?: number;
  agent?: string;
  skillId?: string;
}

export interface ConfigPatch {
  enabledAdapters?: AgentId[];
  liveProbePolicy?: ProbePolicy;
}

export interface RepoStatus {
  initialized: boolean;
  repoRoot: string;
}

export interface PublishedSkill {
  skill_id: string;
  origin_kind: OriginKind;
  hash: string;
  canonical_rel_path: string | null;
}

export interface SkillctlApi {
  repoRoot(): Promise<IpcResult<string>>;
  chooseRepo(): Promise<IpcResult<string | null>>;
  chooseDirectory(): Promise<IpcResult<string | null>>;
  adopt(options: AdoptSkillOptions): Promise<IpcResult<AdoptSkillResult>>;
  readSkillDoc(skillId: string): Promise<IpcResult<string>>;
  setSkillEnabled(skillId: string, enabled: boolean): Promise<IpcResult<boolean>>;
  openPath(target: string): Promise<IpcResult<boolean>>;
  openExternal(url: string): Promise<IpcResult<boolean>>;
  loadConfig(): Promise<IpcResult<SkillctlConfig>>;
  updateConfig(patch: ConfigPatch): Promise<IpcResult<SkillctlConfig>>;
  loadCatalog(): Promise<IpcResult<SkillctlCatalog>>;
  summary(): Promise<IpcResult<CatalogSummary>>;
  taxonomy(): Promise<IpcResult<ManagedSkillTaxonomy>>;
  sources(): Promise<IpcResult<SourcesPayload>>;
  doctor(): Promise<IpcResult<DoctorReport>>;
  adapters(): Promise<IpcResult<AdapterInfo[]>>;
  diff(): Promise<IpcResult<DiffPayload>>;
  verifySources(): Promise<IpcResult<SourceVerificationReport>>;
  discover(): Promise<IpcResult<DiscoverResult>>;
  sync(): Promise<IpcResult<SyncResult>>;
  repair(): Promise<IpcResult<DoctorReport>>;
  prune(): Promise<IpcResult<PruneResult>>;
  bootstrap(): Promise<IpcResult<BootstrapUpstreamResult>>;
  init(): Promise<IpcResult<unknown>>;
  repoStatus(): Promise<IpcResult<RepoStatus>>;
  setSkillMeta(skillId: string, patch: SkillMetaPatch): Promise<IpcResult<boolean>>;
  publish(): Promise<IpcResult<PublishedSkill[]>>;
  skillInstalls(skillId: string): Promise<IpcResult<AgentId[]>>;
  onProgress(cb: (event: ProgressEvent) => void): () => void;
}
