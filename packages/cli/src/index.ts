#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import {
  CATALOG_FILE,
  CONFIG_FILE,
  adoptSkill,
  buildManagedSkillTaxonomy,
  buildSourceRegistry,
  summarizeSourceRegistry,
  verifyCatalogSources,
  discoverCatalog,
  getAdapter,
  initRepo,
  listAdapters,
  bootstrapEmbeddedSkills,
  loadCatalog,
  loadConfig,
  normalizeCatalogArtifacts,
  pruneManaged,
  repairCatalog,
  runDoctor,
  summarizeCatalog,
  syncCatalog,
  writeCatalog,
} from "@skillctl/core";
import { findWorkspaceRoot } from "./repo-root.js";

function usage(): string {
  return `Usage:
  skillctl init
  skillctl discover
  skillctl import
  skillctl adopt --source <path> [--into <category/path>] [--from-repo <repo>] [--skill-path <path>] [--ref <ref>] [--source-type <github|git|local>] [--source-url <url>] [--origin-kind <local-authored|imported-upstream|derived-from-upstream>]
  skillctl sync
  skillctl bootstrap-upstream
  skillctl status
  skillctl diff
  skillctl doctor [--json]
  skillctl repair [--json]
  skillctl prune
  skillctl publish
  skillctl sources [--json]
  skillctl taxonomy [--json]
  skillctl verify-sources [--json]
  skillctl adapters

Notes:
  - Run commands from the skillctl repo root.
  - Only managed public skills are synced into agent directories.
  - Sync and repair default to the embedded upstream skills transport when bootstrapped.
  - Private skills stay in local metadata and are never copied to public agent dirs.`;
}

async function repoRootFromCwd(): Promise<string> {
  return findWorkspaceRoot(process.cwd());
}

async function writeManifestSchemas(repoRoot: string): Promise<void> {
  const schemasDir = path.join(repoRoot, "manifests", "schemas");
  await fs.mkdir(schemasDir, { recursive: true });

  const configSchema = {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    title: "skillctl config",
    type: "object",
    required: ["sourceRoots", "privateRoots", "enabledAdapters", "excludeSkills", "liveProbePolicy"],
    properties: {
      sourceRoots: {
        type: "array",
        items: {
          type: "object",
          required: ["path", "visibility"],
          properties: {
            path: { type: "string" },
            visibility: { enum: ["public", "private"] },
            managedByDefault: { type: "boolean" },
          },
        },
      },
      privateRoots: { type: "array", items: { type: "string" } },
      enabledAdapters: { type: "array", items: { enum: ["claude-code", "codex", "pi", "hermes", "opencode"] } },
      excludeSkills: { type: "array", items: { type: "string" } },
      liveProbePolicy: { enum: ["off", "safe"] },
      transport: {
        type: "object",
        required: ["mode", "command", "args"],
        properties: {
          mode: { enum: ["skills-cli", "copy-fallback"] },
          command: { type: "string" },
          args: { type: "array", items: { type: "string" } },
          embeddedRepoPath: { type: "string" },
        },
      },
      stateDir: { type: "string" },
    },
  };

  const catalogSchema = {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    title: "skillctl catalog",
    type: "object",
    required: ["version", "generatedBy", "skills"],
    properties: {
      version: { type: "integer", minimum: 1 },
      generatedBy: { type: "string" },
      skills: {
        type: "array",
        items: {
          type: "object",
          required: ["skill_id", "visibility", "source_kind", "hash", "targets", "managed"],
          properties: {
            skill_id: { type: "string" },
            display_name: { type: "string" },
            category: {
              enum: [
                "agent-infra",
                "knowledge-and-research",
                "frontend-and-design",
                "deployment-and-platform",
                "productivity-and-artifacts",
                "domain-aws-thrive",
                "system-and-demo",
              ],
            },
            tags: { type: "array", items: { type: "string" } },
            visibility: { enum: ["public", "private"] },
            source_kind: { enum: ["local-public", "local-private", "upstream"] },
            origin_kind: { enum: ["local-authored", "imported-upstream", "derived-from-upstream"] },
            hash: { type: "string" },
            managed: { type: "boolean" },
            targets: { type: "array", items: { enum: ["claude-code", "codex", "pi", "hermes", "opencode"] } },
            canonical_rel_path: { type: "string" },
            aliases: { type: "array", items: { type: "string" } },
            upstream: {
              type: "object",
              properties: {
                repo: { type: "string" },
                ref: { type: "string" },
                skillPath: { type: "string" },
                sourceType: { enum: ["github", "git", "local"] },
                sourceUrl: { type: "string" },
                imported_at: { type: "string" },
                last_verified_ref: { type: "string" },
                local_modifications: { type: "boolean" },
              },
            },
          },
        },
      },
    },
  };

  await fs.writeFile(path.join(schemasDir, "skillctl.config.schema.json"), `${JSON.stringify(configSchema, null, 2)}\n`);
  await fs.writeFile(path.join(schemasDir, "skillctl.catalog.schema.json"), `${JSON.stringify(catalogSchema, null, 2)}\n`);
}

async function ensureInitialized(repoRoot: string): Promise<void> {
  await loadConfig(repoRoot);
  await loadCatalog(repoRoot);
}

async function discoverAndPersist(repoRoot: string): Promise<{ conflicts: Array<{ skillId: string; paths: string[] }>; skills: number }> {
  const config = await loadConfig(repoRoot);
  const current = await loadCatalog(repoRoot);
  const { catalog, conflicts } = await discoverCatalog(repoRoot, config, current);
  await normalizeCatalogArtifacts(repoRoot, catalog);
  await writeCatalog(repoRoot, catalog);
  return { conflicts, skills: catalog.skills.length };
}

async function statusCommand(repoRoot: string): Promise<void> {
  const config = await loadConfig(repoRoot);
  const catalog = await loadCatalog(repoRoot);
  const summary = summarizeCatalog(catalog);
  const taxonomy = buildManagedSkillTaxonomy(catalog);
  const sources = buildSourceRegistry(catalog);
  const sourceSummary = summarizeSourceRegistry(sources);
  console.log(JSON.stringify({
    repoRoot,
    configFile: path.join(repoRoot, CONFIG_FILE),
    catalogFile: path.join(repoRoot, CATALOG_FILE),
    enabledAdapters: config.enabledAdapters.map((agent) => ({
      agent,
      installDir: getAdapter(agent).installDir(),
    })),
    summary,
    taxonomySummary: taxonomy.summary,
    sourceSummary,
  }, null, 2));
}

async function diffCommand(repoRoot: string): Promise<number> {
  const config = await loadConfig(repoRoot);
  const current = await loadCatalog(repoRoot);
  const discovered = await discoverCatalog(repoRoot, config, current);
  const oldMap = new Map(current.skills.map((skill) => [skill.skill_id, skill.hash]));
  const newMap = new Map(discovered.catalog.skills.map((skill) => [skill.skill_id, skill.hash]));

  const changes: Array<{ skill: string; kind: "added" | "removed" | "changed" }> = [];
  for (const [skillId, hash] of newMap) {
    const previous = oldMap.get(skillId);
    if (!previous) {
      changes.push({ skill: skillId, kind: "added" });
    } else if (previous !== hash) {
      changes.push({ skill: skillId, kind: "changed" });
    }
  }
  for (const [skillId] of oldMap) {
    if (!newMap.has(skillId)) {
      changes.push({ skill: skillId, kind: "removed" });
    }
  }

  console.log(JSON.stringify({
    changes,
    conflicts: discovered.conflicts,
  }, null, 2));
  return discovered.conflicts.length > 0 ? 2 : changes.length > 0 ? 1 : 0;
}

async function doctorCommand(repoRoot: string, asJson: boolean): Promise<number> {
  const config = await loadConfig(repoRoot);
  const catalog = await loadCatalog(repoRoot);
  const report = await runDoctor(repoRoot, config, catalog);
  if (asJson) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(`healthy=${report.healthy} exitCode=${report.exitCode}`);
    for (const issue of report.issues) {
      console.log(`[${issue.status}] ${issue.code}: ${issue.detail}`);
    }
    for (const probe of report.probes) {
      console.log(`[probe:${probe.status}] ${probe.agent}: ${probe.detail}`);
    }
  }
  return report.exitCode;
}

async function repairCommand(repoRoot: string, asJson: boolean): Promise<number> {
  const config = await loadConfig(repoRoot);
  const catalog = await loadCatalog(repoRoot);
  await normalizeCatalogArtifacts(repoRoot, catalog);
  await writeCatalog(repoRoot, catalog);
  const report = await repairCatalog(repoRoot, config, catalog);
  await writeCatalog(repoRoot, catalog);
  if (asJson) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(`repair exitCode=${report.exitCode}`);
    for (const action of report.repairActions) {
      console.log(`repair:${action.type} ${action.agent} ${action.skillId ?? ""} ${action.detail}`.trim());
    }
  }
  return report.exitCode;
}

async function syncCommand(repoRoot: string): Promise<void> {
  const config = await loadConfig(repoRoot);
  const catalog = await loadCatalog(repoRoot);
  await normalizeCatalogArtifacts(repoRoot, catalog);
  await writeCatalog(repoRoot, catalog);
  const result = await syncCatalog(repoRoot, config, catalog);
  await writeCatalog(repoRoot, catalog);
  console.log(JSON.stringify(result, null, 2));
}

async function bootstrapUpstreamCommand(repoRoot: string): Promise<void> {
  const config = await loadConfig(repoRoot);
  const result = await bootstrapEmbeddedSkills(config);
  console.log(JSON.stringify({
    repoRoot,
    ...result,
  }, null, 2));
}

async function pruneCommand(repoRoot: string): Promise<void> {
  const config = await loadConfig(repoRoot);
  const catalog = await loadCatalog(repoRoot);
  const result = await pruneManaged(repoRoot, config, catalog);
  console.log(JSON.stringify(result, null, 2));
}

function readFlag(args: string[], flag: string): string | undefined {
  const index = args.indexOf(flag);
  if (index === -1) {
    return undefined;
  }
  return args[index + 1];
}

function hasFlag(args: string[], flag: string): boolean {
  return args.includes(flag);
}

function parseEnumFlag<T extends string>(args: string[], flag: string, allowed: readonly T[]): T | undefined {
  const value = readFlag(args, flag);
  if (value === undefined) {
    return undefined;
  }
  if (!allowed.includes(value as T)) {
    throw new Error(`${flag} must be one of: ${allowed.join(", ")} (got "${value}")`);
  }
  return value as T;
}

async function adoptCommand(repoRoot: string, args: string[]): Promise<void> {
  const sourcePath = readFlag(args, "--source");
  if (!sourcePath) {
    throw new Error("adopt requires --source <path>");
  }

  const config = await loadConfig(repoRoot);
  const catalog = await loadCatalog(repoRoot);
  const result = await adoptSkill(repoRoot, config, catalog, {
    sourcePath,
    destinationSubdir: readFlag(args, "--into"),
    fromRepo: readFlag(args, "--from-repo"),
    skillPath: readFlag(args, "--skill-path"),
    ref: readFlag(args, "--ref"),
    sourceType: parseEnumFlag(args, "--source-type", ["github", "git", "local"] as const),
    sourceUrl: readFlag(args, "--source-url"),
    originKind: parseEnumFlag(args, "--origin-kind", ["local-authored", "imported-upstream", "derived-from-upstream"] as const),
    localModifications: hasFlag(args, "--local-modifications"),
  });

  await writeCatalog(repoRoot, catalog);
  console.log(JSON.stringify(result, null, 2));
}

async function sourcesCommand(repoRoot: string, asJson: boolean): Promise<void> {
  const catalog = await loadCatalog(repoRoot);
  const entries = buildSourceRegistry(catalog);
  const summary = summarizeSourceRegistry(entries);
  if (asJson) {
    console.log(JSON.stringify({ summary, sources: entries }, null, 2));
    return;
  }
  for (const entry of entries) {
    console.log(`${entry.skill_id}\t${entry.category_label}\t${entry.origin_kind}\t${entry.upstream_repo ?? "n/a"}\t${entry.upstream_path ?? "n/a"}\t${entry.ref ?? "n/a"}\t${entry.local_modifications ? "yes" : "no"}`);
  }
}

async function taxonomyCommand(repoRoot: string, asJson: boolean): Promise<void> {
  const catalog = await loadCatalog(repoRoot);
  const taxonomy = buildManagedSkillTaxonomy(catalog);
  if (asJson) {
    console.log(JSON.stringify(taxonomy, null, 2));
    return;
  }

  for (const category of taxonomy.categories) {
    console.log(`${category.label} (${category.skillCount})`);
    for (const skill of category.skills) {
      const tags = skill.tags.length > 0 ? ` [${skill.tags.join(", ")}]` : "";
      console.log(`  - ${skill.skill_id}${tags}`);
    }
  }
}

async function verifySourcesCommand(repoRoot: string, asJson: boolean): Promise<number> {
  const catalog = await loadCatalog(repoRoot);
  const report = await verifyCatalogSources(catalog);
  if (asJson) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    for (const result of report.results) {
      console.log(`[${result.status}] ${result.skill_id}: ${result.detail}${result.resolved_ref ? ` (${result.resolved_ref})` : ""}`);
    }
  }
  return report.ok ? 0 : 1;
}

async function publishCommand(repoRoot: string): Promise<void> {
  const catalog = await loadCatalog(repoRoot);
  const published = catalog.skills
    .filter((skill) => skill.visibility === "public" && skill.source_kind !== "local-private")
    .map((skill) => ({
      skill_id: skill.skill_id,
      origin_kind: skill.origin_kind,
      hash: skill.hash,
      canonical_rel_path: skill.canonical_rel_path,
      upstream: skill.upstream ?? null,
    }));
  console.log(JSON.stringify({ published }, null, 2));
}

async function adaptersCommand(): Promise<void> {
  console.log(JSON.stringify(listAdapters(), null, 2));
}

async function main(): Promise<void> {
  const [command, ...args] = process.argv.slice(2);
  const repoRoot = await repoRootFromCwd();

  switch (command) {
    case "init": {
      const result = await initRepo(repoRoot);
      await writeManifestSchemas(repoRoot);
      console.log(JSON.stringify(result, null, 2));
      return;
    }
    case "discover":
    case "import": {
      await ensureInitialized(repoRoot);
      const result = await discoverAndPersist(repoRoot);
      console.log(JSON.stringify(result, null, 2));
      process.exitCode = result.conflicts.length > 0 ? 2 : 0;
      return;
    }
    case "adopt": {
      await ensureInitialized(repoRoot);
      await adoptCommand(repoRoot, args);
      return;
    }
    case "sync": {
      await ensureInitialized(repoRoot);
      await syncCommand(repoRoot);
      return;
    }
    case "bootstrap-upstream": {
      await ensureInitialized(repoRoot);
      await bootstrapUpstreamCommand(repoRoot);
      return;
    }
    case "status": {
      await ensureInitialized(repoRoot);
      await statusCommand(repoRoot);
      return;
    }
    case "diff": {
      await ensureInitialized(repoRoot);
      process.exitCode = await diffCommand(repoRoot);
      return;
    }
    case "doctor": {
      await ensureInitialized(repoRoot);
      process.exitCode = await doctorCommand(repoRoot, args.includes("--json"));
      return;
    }
    case "repair": {
      await ensureInitialized(repoRoot);
      process.exitCode = await repairCommand(repoRoot, args.includes("--json"));
      return;
    }
    case "prune": {
      await ensureInitialized(repoRoot);
      await pruneCommand(repoRoot);
      return;
    }
    case "publish": {
      await ensureInitialized(repoRoot);
      await publishCommand(repoRoot);
      return;
    }
    case "sources": {
      await ensureInitialized(repoRoot);
      await sourcesCommand(repoRoot, args.includes("--json"));
      return;
    }
    case "taxonomy": {
      await ensureInitialized(repoRoot);
      await taxonomyCommand(repoRoot, args.includes("--json"));
      return;
    }
    case "verify-sources": {
      await ensureInitialized(repoRoot);
      process.exitCode = await verifySourcesCommand(repoRoot, args.includes("--json"));
      return;
    }
    case "adapters": {
      await adaptersCommand();
      return;
    }
    default: {
      console.log(usage());
    }
  }
}

main().catch((error) => {
  const message = error instanceof Error ? error.stack ?? error.message : String(error);
  console.error(message);
  process.exitCode = 2;
});
