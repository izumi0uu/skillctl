import { z } from "zod";

export const agentIdSchema = z.enum(["claude-code", "codex", "pi", "hermes", "opencode"]);
export const visibilitySchema = z.enum(["public", "private"]);
export const sourceKindSchema = z.enum(["local-public", "local-private", "upstream"]);
export const probePolicySchema = z.enum(["off", "safe"]);
export const transportModeSchema = z.enum(["skills-cli", "copy-fallback"]);

export const transportSchema = z.object({
  mode: transportModeSchema.default("skills-cli"),
  command: z.string().min(1).default("npx"),
  args: z.array(z.string()).default(["--yes", "skills"]),
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
  }),
  stateDir: z.string().optional(),
});

export const upstreamSourceSchema = z.object({
  repo: z.string().min(1),
  ref: z.string().min(1),
  skillPath: z.string().min(1),
  sourceType: z.enum(["github", "git", "local"]),
  sourceUrl: z.string().optional(),
});

export const catalogSkillSchema = z.object({
  skill_id: z.string().min(1),
  display_name: z.string().optional(),
  visibility: visibilitySchema,
  source_kind: sourceKindSchema,
  hash: z.string().min(1),
  managed: z.boolean(),
  targets: z.array(agentIdSchema),
  canonical_rel_path: z.string().optional(),
  upstream: upstreamSourceSchema.optional(),
  aliases: z.array(z.string()).optional(),
});

export const skillctlCatalogSchema = z.object({
  version: z.number().int().positive(),
  generatedBy: z.string().min(1),
  skills: z.array(catalogSkillSchema),
});

export const managedSkillIndexEntrySchema = z.object({
  skill_id: z.string().min(1),
  hash: z.string().min(1),
  managedAt: z.string().min(1),
});

export const managedSkillIndexSchema = z.object({
  version: z.number().int().positive(),
  agent: agentIdSchema,
  entries: z.array(managedSkillIndexEntrySchema),
});
