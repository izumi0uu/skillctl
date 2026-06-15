import { readFile } from "node:fs/promises";
import { join } from "node:path";

import { BrowserWindow, dialog, ipcMain, shell } from "electron";
import {
  adoptSkill,
  bootstrapEmbeddedSkills,
  buildManagedSkillTaxonomy,
  buildSourceRegistry,
  discoverCatalog,
  listAdapters,
  loadCatalog,
  loadConfig,
  normalizeCatalogArtifacts,
  patchConfigFields,
  pruneManaged,
  repairCatalog,
  runDoctor,
  summarizeCatalog,
  summarizeSourceRegistry,
  syncCatalog,
  verifyCatalogSources,
  writeCatalog,
} from "@skillctl/core";
import type { AdoptSkillOptions } from "@skillctl/core";

import {
  CHANNELS,
  type ConfigPatch,
  type DiffChange,
  type IpcResult,
  type ProgressEvent,
} from "../shared/ipc-contract";
import { chooseRepoRoot, getRepoRoot, resolveInitialRepoRoot } from "./repo-root";

async function envelope<T>(fn: () => Promise<T>): Promise<IpcResult<T>> {
  try {
    return { ok: true, data: await fn() };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : String(error) };
  }
}

function emitProgress(event: ProgressEvent): void {
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send(CHANNELS.progress, event);
  }
}

async function withProgress<T>(op: string, fn: () => Promise<T>): Promise<T> {
  emitProgress({ op, phase: "started" });
  try {
    const result = await fn();
    emitProgress({ op, phase: "finished" });
    return result;
  } catch (error) {
    emitProgress({ op, phase: "error", detail: error instanceof Error ? error.message : String(error) });
    throw error;
  }
}

export function registerIpcHandlers(): void {
  ipcMain.handle(CHANNELS.repoRoot, () => envelope(() => resolveInitialRepoRoot()));
  ipcMain.handle(CHANNELS.chooseRepo, () => envelope(() => chooseRepoRoot()));

  ipcMain.handle(CHANNELS.chooseDirectory, () =>
    envelope(async () => {
      const result = await dialog.showOpenDialog({
        properties: ["openDirectory"],
        title: "Select a skill folder",
      });
      return result.canceled || result.filePaths.length === 0 ? null : result.filePaths[0];
    }),
  );

  ipcMain.handle(CHANNELS.adopt, (_event, options: AdoptSkillOptions) =>
    envelope(() =>
      withProgress("adopt", async () => {
        const repoRoot = getRepoRoot();
        const config = await loadConfig(repoRoot);
        const catalog = await loadCatalog(repoRoot);
        const result = await adoptSkill(repoRoot, config, catalog, options);
        await writeCatalog(repoRoot, catalog);
        return result;
      }),
    ),
  );

  ipcMain.handle(CHANNELS.readSkillDoc, (_event, skillId: string) =>
    envelope(async () => {
      const repoRoot = getRepoRoot();
      const catalog = await loadCatalog(repoRoot);
      const skill = catalog.skills.find((entry) => entry.skill_id === skillId);
      if (!skill?.canonical_rel_path) {
        throw new Error(`no canonical path for ${skillId}`);
      }
      return readFile(join(repoRoot, skill.canonical_rel_path, "SKILL.md"), "utf8");
    }),
  );

  ipcMain.handle(CHANNELS.openPath, (_event, target: string) =>
    envelope(async () => {
      const error = await shell.openPath(target);
      if (error) {
        throw new Error(error);
      }
      return true;
    }),
  );

  ipcMain.handle(CHANNELS.openExternal, (_event, url: string) =>
    envelope(async () => {
      await shell.openExternal(url);
      return true;
    }),
  );

  ipcMain.handle(CHANNELS.loadConfig, () => envelope(() => loadConfig(getRepoRoot())));
  ipcMain.handle(CHANNELS.updateConfig, (_event, patch: ConfigPatch) =>
    envelope(async () => {
      const repoRoot = getRepoRoot();
      await patchConfigFields(repoRoot, patch);
      return loadConfig(repoRoot);
    }),
  );
  ipcMain.handle(CHANNELS.loadCatalog, () => envelope(() => loadCatalog(getRepoRoot())));

  ipcMain.handle(CHANNELS.summary, () =>
    envelope(async () => {
      const catalog = await loadCatalog(getRepoRoot());
      return summarizeCatalog(catalog);
    }),
  );

  ipcMain.handle(CHANNELS.taxonomy, () =>
    envelope(async () => {
      const catalog = await loadCatalog(getRepoRoot());
      return buildManagedSkillTaxonomy(catalog);
    }),
  );

  ipcMain.handle(CHANNELS.sources, () =>
    envelope(async () => {
      const catalog = await loadCatalog(getRepoRoot());
      const sources = buildSourceRegistry(catalog);
      return { summary: summarizeSourceRegistry(sources), sources };
    }),
  );

  ipcMain.handle(CHANNELS.doctor, () =>
    envelope(async () => {
      const repoRoot = getRepoRoot();
      const config = await loadConfig(repoRoot);
      const catalog = await loadCatalog(repoRoot);
      return runDoctor(repoRoot, config, catalog);
    }),
  );

  ipcMain.handle(CHANNELS.adapters, () =>
    envelope(async () =>
      listAdapters().map((adapter) => ({
        id: adapter.id,
        label: adapter.label,
        installDir: adapter.installDir(),
        canProbe: adapter.canProbe,
      })),
    ),
  );

  ipcMain.handle(CHANNELS.diff, () =>
    envelope(async () => {
      const repoRoot = getRepoRoot();
      const config = await loadConfig(repoRoot);
      const current = await loadCatalog(repoRoot);
      const discovered = await discoverCatalog(repoRoot, config, current);
      const oldMap = new Map(current.skills.map((skill) => [skill.skill_id, skill.hash]));
      const newMap = new Map(discovered.catalog.skills.map((skill) => [skill.skill_id, skill.hash]));
      const changes: DiffChange[] = [];
      for (const [id, hash] of newMap) {
        const previous = oldMap.get(id);
        if (!previous) {
          changes.push({ skill: id, kind: "added" });
        } else if (previous !== hash) {
          changes.push({ skill: id, kind: "changed" });
        }
      }
      for (const [id] of oldMap) {
        if (!newMap.has(id)) {
          changes.push({ skill: id, kind: "removed" });
        }
      }
      return { changes, conflicts: discovered.conflicts };
    }),
  );

  ipcMain.handle(CHANNELS.verifySources, () =>
    envelope(async () => {
      const catalog = await loadCatalog(getRepoRoot());
      return verifyCatalogSources(catalog);
    }),
  );

  ipcMain.handle(CHANNELS.discover, () =>
    envelope(() =>
      withProgress("discover", async () => {
        const repoRoot = getRepoRoot();
        const config = await loadConfig(repoRoot);
        const current = await loadCatalog(repoRoot);
        const { catalog, conflicts } = await discoverCatalog(repoRoot, config, current);
        await normalizeCatalogArtifacts(repoRoot, catalog);
        await writeCatalog(repoRoot, catalog);
        return { conflicts, skills: catalog.skills.length };
      }),
    ),
  );

  ipcMain.handle(CHANNELS.sync, () =>
    envelope(() =>
      withProgress("sync", async () => {
        const repoRoot = getRepoRoot();
        const config = await loadConfig(repoRoot);
        const catalog = await loadCatalog(repoRoot);
        await normalizeCatalogArtifacts(repoRoot, catalog);
        await writeCatalog(repoRoot, catalog);
        const result = await syncCatalog(repoRoot, config, catalog, (event) => {
          emitProgress({
            op: "sync",
            phase: "step",
            stage: event.stage,
            current: event.copied,
            total: event.total,
            agent: event.agent,
            skillId: event.skillId,
            detail: event.message,
          });
        });
        await writeCatalog(repoRoot, catalog);
        return result;
      }),
    ),
  );

  ipcMain.handle(CHANNELS.repair, () =>
    envelope(() =>
      withProgress("repair", async () => {
        const repoRoot = getRepoRoot();
        const config = await loadConfig(repoRoot);
        const catalog = await loadCatalog(repoRoot);
        await normalizeCatalogArtifacts(repoRoot, catalog);
        await writeCatalog(repoRoot, catalog);
        const report = await repairCatalog(repoRoot, config, catalog, (event) => {
          emitProgress({
            op: "repair",
            phase: "step",
            stage: event.stage,
            current: event.copied,
            total: event.total,
            agent: event.agent,
            skillId: event.skillId,
            detail: event.message,
          });
        });
        await writeCatalog(repoRoot, catalog);
        return report;
      }),
    ),
  );

  ipcMain.handle(CHANNELS.prune, () =>
    envelope(() =>
      withProgress("prune", async () => {
        const repoRoot = getRepoRoot();
        const config = await loadConfig(repoRoot);
        const catalog = await loadCatalog(repoRoot);
        return pruneManaged(repoRoot, config, catalog, (event) => {
          emitProgress({
            op: "prune",
            phase: "step",
            stage: event.stage,
            current: event.removed,
            agent: event.agent,
            skillId: event.skillId,
          });
        });
      }),
    ),
  );

  ipcMain.handle(CHANNELS.bootstrap, () =>
    envelope(() =>
      withProgress("bootstrap", async () => {
        const config = await loadConfig(getRepoRoot());
        return bootstrapEmbeddedSkills(config, (event) => {
          emitProgress({ op: "bootstrap", phase: "step", stage: event.stage, detail: event.message });
        });
      }),
    ),
  );
}
