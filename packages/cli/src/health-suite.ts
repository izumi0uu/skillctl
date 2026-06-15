#!/usr/bin/env node
import process from "node:process";
import { pathToFileURL } from "node:url";

import {
  loadCatalog,
  loadConfig,
  normalizeCatalogArtifacts,
  runDoctor,
  summarizeCatalog,
  syncCatalog,
  verifyCatalogSources,
  writeCatalog,
  discoverCatalog,
} from "@skillctl/core";
import { findWorkspaceRoot } from "./repo-root.js";

interface HealthSuiteStepResult {
  name: "discover" | "sync" | "doctor" | "verify-sources";
  ok: boolean;
  exitCode: 0 | 1 | 2;
  detail: string;
}

interface HealthSuiteReport {
  repoRoot: string;
  ok: boolean;
  exitCode: 0 | 1 | 2;
  steps: HealthSuiteStepResult[];
  summary: {
    catalog: ReturnType<typeof summarizeCatalog>;
    discover: {
      skills: number;
      conflicts: Array<{ skillId: string; paths: string[] }>;
    };
    sync: {
      copied: number;
      skipped: number;
      managedIndexesUpdated: number;
      transportRuns: number;
    };
    doctor: {
      healthy: boolean;
      exitCode: 0 | 1 | 2;
      issueCount: number;
      repairableIssueCount: number;
    };
    verifySources: {
      ok: boolean;
      okCount: number;
      skipCount: number;
      warnCount: number;
      errorCount: number;
    };
  };
}

function maxExitCode(...codes: Array<0 | 1 | 2>): 0 | 1 | 2 {
  return codes.reduce<0 | 1 | 2>((max, code) => (code > max ? code : max), 0);
}

export type { HealthSuiteReport, HealthSuiteStepResult };

export async function runHealthSuite(repoRoot: string): Promise<HealthSuiteReport> {
  const config = await loadConfig(repoRoot);

  const currentCatalog = await loadCatalog(repoRoot);
  const discovered = await discoverCatalog(repoRoot, config, currentCatalog);
  if (discovered.conflicts.length > 0) {
    return {
      repoRoot,
      ok: false,
      exitCode: 2,
      steps: [
        {
          name: "discover",
          ok: false,
          exitCode: 2,
          detail: `discovery found ${discovered.conflicts.length} skill-id conflict(s); downstream steps skipped`,
        },
        {
          name: "sync",
          ok: false,
          exitCode: 2,
          detail: "skipped because discovery conflicts must be resolved before sync",
        },
        {
          name: "doctor",
          ok: false,
          exitCode: 2,
          detail: "skipped because discovery conflicts must be resolved before doctor",
        },
        {
          name: "verify-sources",
          ok: false,
          exitCode: 2,
          detail: "skipped because discovery conflicts must be resolved before source verification",
        },
      ],
      summary: {
        catalog: summarizeCatalog(currentCatalog),
        discover: {
          skills: discovered.catalog.skills.length,
          conflicts: discovered.conflicts,
        },
        sync: {
          copied: 0,
          skipped: 0,
          managedIndexesUpdated: 0,
          transportRuns: 0,
        },
        doctor: {
          healthy: false,
          exitCode: 2,
          issueCount: 0,
          repairableIssueCount: 0,
        },
        verifySources: {
          ok: false,
          okCount: 0,
          skipCount: 0,
          warnCount: 0,
          errorCount: 0,
        },
      },
    };
  }

  await normalizeCatalogArtifacts(repoRoot, discovered.catalog);
  await writeCatalog(repoRoot, discovered.catalog);

  const syncResult = await syncCatalog(repoRoot, config, discovered.catalog);
  await writeCatalog(repoRoot, discovered.catalog);

  const doctorReport = await runDoctor(repoRoot, config, discovered.catalog);
  const verifySourcesReport = await verifyCatalogSources(discovered.catalog);

  const verifyWarnCount = verifySourcesReport.results.filter((result) => result.status === "warn").length;
  const verifyErrorCount = verifySourcesReport.results.filter((result) => result.status === "error").length;
  const verifySkipCount = verifySourcesReport.results.filter((result) => result.status === "skip").length;
  const verifyOkCount = verifySourcesReport.results.filter((result) => result.status === "ok").length;
  const verifyExitCode: 0 | 1 | 2 = verifyErrorCount > 0 ? 2 : verifyWarnCount > 0 ? 1 : 0;

  const steps: HealthSuiteStepResult[] = [
    {
      name: "discover",
      ok: discovered.conflicts.length === 0,
      exitCode: discovered.conflicts.length > 0 ? 2 : 0,
      detail: discovered.conflicts.length > 0
        ? `discovery found ${discovered.conflicts.length} skill-id conflict(s)`
        : `discovered ${discovered.catalog.skills.length} skill(s)`,
    },
    {
      name: "sync",
      ok: true,
      exitCode: 0,
      detail: `copied ${syncResult.copied.length}, skipped ${syncResult.skipped.length}, updated ${syncResult.managedIndexesUpdated.length} managed index(es)`,
    },
    {
      name: "doctor",
      ok: doctorReport.exitCode === 0,
      exitCode: doctorReport.exitCode,
      detail: doctorReport.healthy
        ? "doctor reports healthy state"
        : `doctor reported ${doctorReport.issues.length} issue(s)`,
    },
    {
      name: "verify-sources",
      ok: verifySourcesReport.ok,
      exitCode: verifyExitCode,
      detail: `verified ${verifyOkCount} ok, ${verifySkipCount} skipped, ${verifyWarnCount} warn, ${verifyErrorCount} error`,
    },
  ];

  const exitCode = maxExitCode(...steps.map((step) => step.exitCode));
  const report: HealthSuiteReport = {
    repoRoot,
    ok: exitCode === 0,
    exitCode,
    steps,
    summary: {
      catalog: summarizeCatalog(discovered.catalog),
      discover: {
        skills: discovered.catalog.skills.length,
        conflicts: discovered.conflicts,
      },
      sync: {
        copied: syncResult.copied.length,
        skipped: syncResult.skipped.length,
        managedIndexesUpdated: syncResult.managedIndexesUpdated.length,
        transportRuns: syncResult.transportRuns?.length ?? 0,
      },
      doctor: {
        healthy: doctorReport.healthy,
        exitCode: doctorReport.exitCode,
        issueCount: doctorReport.issues.length,
        repairableIssueCount: doctorReport.issues.filter((issue) => issue.repairable).length,
      },
      verifySources: {
        ok: verifySourcesReport.ok,
        okCount: verifyOkCount,
        skipCount: verifySkipCount,
        warnCount: verifyWarnCount,
        errorCount: verifyErrorCount,
      },
    },
  };

  return report;
}

async function main(): Promise<void> {
  const repoRoot = await findWorkspaceRoot(process.cwd());
  const report = await runHealthSuite(repoRoot);
  console.log(JSON.stringify(report, null, 2));
  process.exitCode = report.exitCode;
}

const entrypoint = process.argv[1];
if (entrypoint && import.meta.url === pathToFileURL(entrypoint).href) {
  main().catch((error) => {
    const message = error instanceof Error ? error.stack ?? error.message : String(error);
    console.error(message);
    process.exitCode = 2;
  });
}
