#!/usr/bin/env node
import path from "node:path";
import process from "node:process";
import { performance } from "node:perf_hooks";
import { pathToFileURL } from "node:url";

import {
  loadCatalog,
  loadConfig,
  normalizeCatalogArtifacts,
  summarizeCatalog,
  syncCatalog,
  writeCatalog,
} from "@skillctl/core";
import { findWorkspaceRoot } from "./repo-root.js";

function parseInteger(value: string | undefined, fallback: number): number {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseArgs(argv: string[]): {
  iterations: number;
  warmup: number;
  json: boolean;
  repoRoot: string;
  label: string | null;
} {
  const options = {
    iterations: 5,
    warmup: 1,
    json: false,
    repoRoot: "",
    label: null as string | null,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--") {
      continue;
    }
    if (arg === "--iterations" || arg === "-n") {
      options.iterations = parseInteger(argv[i + 1], options.iterations);
      i += 1;
      continue;
    }
    if (arg === "--warmup" || arg === "-w") {
      options.warmup = parseInteger(argv[i + 1], options.warmup);
      i += 1;
      continue;
    }
    if (arg === "--repo") {
      options.repoRoot = path.resolve(argv[i + 1] ?? options.repoRoot);
      i += 1;
      continue;
    }
    if (arg === "--label") {
      options.label = argv[i + 1] ?? null;
      i += 1;
      continue;
    }
    if (arg === "--json") {
      options.json = true;
    }
  }

  return options;
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}

function percentile(sortedValues: number[], p: number): number {
  if (sortedValues.length === 0) {
    return 0;
  }
  const index = Math.min(sortedValues.length - 1, Math.max(0, Math.ceil((p / 100) * sortedValues.length) - 1));
  return sortedValues[index] ?? 0;
}

function summarizeDurations(durations: number[]) {
  const sorted = [...durations].sort((a, b) => a - b);
  const total = sorted.reduce((sum, value) => sum + value, 0);
  return {
    minMs: round(sorted[0] ?? 0),
    medianMs: round(percentile(sorted, 50)),
    p95Ms: round(percentile(sorted, 95)),
    maxMs: round(sorted[sorted.length - 1] ?? 0),
    meanMs: round(sorted.length > 0 ? total / sorted.length : 0),
  };
}

async function runOnce(repoRoot: string) {
  const config = await loadConfig(repoRoot);
  const catalog = await loadCatalog(repoRoot);
  const normalized = await normalizeCatalogArtifacts(repoRoot, catalog);
  if (normalized.catalogChanged || normalized.readmeChanged) {
    await writeCatalog(repoRoot, catalog);
  }

  const startedAt = performance.now();
  const result = await syncCatalog(repoRoot, config, catalog);
  const durationMs = performance.now() - startedAt;

  return {
    durationMs: round(durationMs),
    copied: result.copied.length,
    skipped: result.skipped.length,
    managedIndexesUpdated: result.managedIndexesUpdated.length,
    transportRuns: result.transportRuns?.length ?? 0,
    perAgentCopied: Object.fromEntries(
      Object.entries(
        result.copied.reduce<Record<string, number>>((acc, entry) => {
          acc[entry.agent] = (acc[entry.agent] ?? 0) + 1;
          return acc;
        }, {}),
      ).sort(([a], [b]) => a.localeCompare(b)),
    ),
  };
}

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  if (!options.repoRoot) {
    options.repoRoot = await findWorkspaceRoot(process.cwd());
  }
  const config = await loadConfig(options.repoRoot);
  const catalog = await loadCatalog(options.repoRoot);
  const summary = summarizeCatalog(catalog);
  const warmups = [];
  const runs = [];

  for (let i = 0; i < options.warmup; i += 1) {
    warmups.push(await runOnce(options.repoRoot));
  }

  for (let i = 0; i < options.iterations; i += 1) {
    runs.push(await runOnce(options.repoRoot));
  }

  const durations = runs.map((run) => run.durationMs);
  const aggregate = {
    ...summarizeDurations(durations),
    averageTransportRuns: round(
      runs.reduce((sum, run) => sum + run.transportRuns, 0) / Math.max(1, runs.length),
    ),
  };

  const report = {
    label: options.label,
    repoRoot: options.repoRoot,
    config: {
      transportMode: config.transport.mode,
      enabledAdapters: config.enabledAdapters,
      embeddedRepoPath: config.transport.embeddedRepoPath ?? null,
    },
    catalog: {
      managedSkills: summary.managedSkills,
      publicSkills: summary.publicSkills,
      privateSkills: summary.privateSkills,
      upstreamSkills: summary.upstreamSkills,
    },
    benchmark: {
      warmupIterations: options.warmup,
      measuredIterations: options.iterations,
    },
    warmups,
    runs,
    aggregate,
  };

  if (options.json) {
    console.log(JSON.stringify(report, null, 2));
    return;
  }

  console.log(`sync benchmark${options.label ? ` (${options.label})` : ""}`);
  console.log(`repo: ${report.repoRoot}`);
  console.log(`transport: ${report.config.transportMode}`);
  console.log(`adapters: ${report.config.enabledAdapters.join(", ")}`);
  console.log(`catalog: public=${report.catalog.publicSkills}, managed=${report.catalog.managedSkills}`);
  console.log(`warmup iterations: ${report.benchmark.warmupIterations}`);
  console.log(`measured iterations: ${report.benchmark.measuredIterations}`);
  console.log("");

  for (const [index, run] of runs.entries()) {
    console.log(
      `run ${index + 1}: ${run.durationMs}ms | copied=${run.copied} skipped=${run.skipped} transportRuns=${run.transportRuns}`,
    );
  }

  console.log("");
  console.log(
    `aggregate: min=${aggregate.minMs}ms median=${aggregate.medianMs}ms mean=${aggregate.meanMs}ms p95=${aggregate.p95Ms}ms max=${aggregate.maxMs}ms avgTransportRuns=${aggregate.averageTransportRuns}`,
  );
}

const entrypoint = process.argv[1];
if (entrypoint && import.meta.url === pathToFileURL(entrypoint).href) {
  main().catch((error) => {
    const message = error instanceof Error ? error.stack ?? error.message : String(error);
    console.error(message);
    process.exitCode = 1;
  });
}
