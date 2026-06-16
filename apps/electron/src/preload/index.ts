import { contextBridge, ipcRenderer } from "electron";

import { CHANNELS, type ConfigPatch, type ProgressEvent, type SkillctlApi } from "../shared/ipc-contract";
import type { AdoptSkillOptions, SkillMetaPatch } from "@skillctl/core";

const api: SkillctlApi = {
  repoRoot: () => ipcRenderer.invoke(CHANNELS.repoRoot),
  chooseRepo: () => ipcRenderer.invoke(CHANNELS.chooseRepo),
  chooseDirectory: () => ipcRenderer.invoke(CHANNELS.chooseDirectory),
  adopt: (options: AdoptSkillOptions) => ipcRenderer.invoke(CHANNELS.adopt, options),
  readSkillDoc: (skillId: string) => ipcRenderer.invoke(CHANNELS.readSkillDoc, skillId),
  setSkillEnabled: (skillId: string, enabled: boolean) => ipcRenderer.invoke(CHANNELS.setSkillEnabled, skillId, enabled),
  openPath: (target: string) => ipcRenderer.invoke(CHANNELS.openPath, target),
  openExternal: (url: string) => ipcRenderer.invoke(CHANNELS.openExternal, url),
  loadConfig: () => ipcRenderer.invoke(CHANNELS.loadConfig),
  updateConfig: (patch: ConfigPatch) => ipcRenderer.invoke(CHANNELS.updateConfig, patch),
  loadCatalog: () => ipcRenderer.invoke(CHANNELS.loadCatalog),
  summary: () => ipcRenderer.invoke(CHANNELS.summary),
  taxonomy: () => ipcRenderer.invoke(CHANNELS.taxonomy),
  sources: () => ipcRenderer.invoke(CHANNELS.sources),
  doctor: () => ipcRenderer.invoke(CHANNELS.doctor),
  adapters: () => ipcRenderer.invoke(CHANNELS.adapters),
  diff: () => ipcRenderer.invoke(CHANNELS.diff),
  verifySources: () => ipcRenderer.invoke(CHANNELS.verifySources),
  discover: () => ipcRenderer.invoke(CHANNELS.discover),
  sync: () => ipcRenderer.invoke(CHANNELS.sync),
  repair: () => ipcRenderer.invoke(CHANNELS.repair),
  prune: () => ipcRenderer.invoke(CHANNELS.prune),
  bootstrap: () => ipcRenderer.invoke(CHANNELS.bootstrap),
  init: () => ipcRenderer.invoke(CHANNELS.init),
  repoStatus: () => ipcRenderer.invoke(CHANNELS.repoStatus),
  setSkillMeta: (skillId: string, patch: SkillMetaPatch) => ipcRenderer.invoke(CHANNELS.setSkillMeta, skillId, patch),
  publish: () => ipcRenderer.invoke(CHANNELS.publish),
  skillInstalls: (skillId: string) => ipcRenderer.invoke(CHANNELS.skillInstalls, skillId),
  onProgress: (cb: (event: ProgressEvent) => void) => {
    const listener = (_event: unknown, payload: ProgressEvent) => cb(payload);
    ipcRenderer.on(CHANNELS.progress, listener);
    return () => {
      ipcRenderer.removeListener(CHANNELS.progress, listener);
    };
  },
};

contextBridge.exposeInMainWorld("skillctl", api);
