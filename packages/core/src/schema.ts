import { z } from "zod";

export const agentIdSchema = z.enum(["claude-code", "codex", "pi", "hermes", "opencode"]);
export const visibilitySchema = z.enum(["public", "private"]);
export const sourceKindSchema = z.enum(["local-public", "local-private", "upstream"]);
export const originKindSchema = z.enum(["local-authored", "imported-upstream", "derived-from-upstream"]);
export const probePolicySchema = z.enum(["off", "safe"]);
export const transportModeSchema = z.enum(["skills-cli", "copy-fallback"]);
export const skillCategorySchema = z.enum([
  "agent-infra",
  "knowledge-and-research",
  "frontend-and-design",
  "deployment-and-platform",
  "productivity-and-artifacts",
  "domain-aws-thrive",
  "system-and-demo",
]);

export const transportSchema = z.object({
  mode: transportModeSchema.default("skills-cli"),
  command: z.string().min(1).default("npx"),
  args: z.array(z.string()).default(["--yes", "skills"]),
  embeddedRepoPath: z.string().min(1).optional(),
});

export const sourceRootSchema = z.object({
  path: z.string().min(1),
  visibility: visibilitySchema,
  managedByDefault: z.boolean().optional(),
});

export const skillctlConfigSchema = z.object({
  sourceRoots: z.array(sourceRootSchema),
  privateRoots: z.array(z.string()).default([]),
  enabledAdapters: z.array(agentIdSchema),
  excludeSkills: z.array(z.string()).default([]),
  liveProbePolicy: probePolicySchema.default("off"),
  transport: transportSchema.default({
    mode: "skills-cli",
    command: "npx",
    args: ["--yes", "skills"],
    embeddedRepoPath: "vercel-skills",
  }),
  stateDir: z.string().optional(),
});

export const upstreamSourceSchema = z.object({
  repo: z.string().min(1).optional(),
  ref: z.string().min(1).optional(),
  skillPath: z.string().min(1).optional(),
  sourceType: z.enum(["github", "git", "local"]).optional(),
  sourceUrl: z.string().optional(),
  imported_at: z.string().optional(),
  last_verified_ref: z.string().optional(),
  local_modifications: z.boolean().optional(),
});

export const catalogSkillSchema = z.object({
  skill_id: z.string().min(1),
  display_name: z.string().optional(),
  category: skillCategorySchema.optional(),
  tags: z.array(z.string()).optional(),
  visibility: visibilitySchema,
  source_kind: sourceKindSchema,
  origin_kind: originKindSchema.default("local-authored"),
  hash: z.string().min(1),
  managed: z.boolean(),
  enabled: z.boolean().optional(),
  targets: z.array(agentIdSchema),
  canonical_rel_path: z.string().optional(),
  upstream: upstreamSourceSchema.optional(),
  aliases: z.array(z.string()).optional(),
  distribution: z.object({
    portability_allow_targets: z.array(agentIdSchema).optional(),
  }).optional(),
});

export const skillctlCatalogSchema = z.object({
  version: z.number().int().positive(),
  generatedBy: z.string().min(1),
  skills: z.array(catalogSkillSchema),
});

export const repoReferenceModeSchema = z.enum(["reference-only"]);
export const repoReferenceSourceTypeSchema = z.enum(["github", "git", "local"]);

export const repoReferenceEntrySchema = z.object({
  id: z.string().min(1),
  display_name: z.string().min(1).optional(),
  category: skillCategorySchema.optional(),
  tags: z.array(z.string().min(1)).optional(),
  mode: repoReferenceModeSchema.default("reference-only"),
  repo: z.string().min(1).optional(),
  ref: z.string().min(1).optional(),
  sourceType: repoReferenceSourceTypeSchema,
  sourceUrl: z.string().min(1),
  primarySkillPaths: z.array(z.string().min(1)).min(1),
  referencePaths: z.array(z.string().min(1)).optional(),
  why: z.string().min(1),
  notes: z.string().min(1).optional(),
});

export const repoReferenceRegistrySchema = z.object({
  version: z.number().int().positive(),
  generatedBy: z.string().min(1),
  references: z.array(repoReferenceEntrySchema),
});

export const managedSkillIndexEntrySchema = z.object({
  skill_id: z.string().min(1),
  hash: z.string().min(1),
  source_hash: z.string().optional(),
  rendered_hash: z.string().optional(),
  managedAt: z.string().min(1),
});

export const managedSkillIndexSchema = z.object({
  version: z.number().int().positive(),
  agent: agentIdSchema,
  entries: z.array(managedSkillIndexEntrySchema),
});
