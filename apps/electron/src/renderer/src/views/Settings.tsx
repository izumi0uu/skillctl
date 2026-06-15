import { Computer, Folder, Search } from "iconoir-react";
import type { AgentId } from "@skillctl/core";

import { Button, cn, Panel, Row, Spinner, useUi } from "../components/ui";
import { api, useAsync } from "../lib/api";

function PathRow({ label, value, onOpen }: { label: string; value?: string | null; onOpen: (value: string) => void }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-ink/8 pb-1.5 last:border-none last:pb-0">
      <span className="font-semibold text-ink-soft">{label}</span>
      {value ? (
        <button
          type="button"
          title="Open in Finder"
          onClick={() => onOpen(value)}
          className="truncate rounded font-bold text-blue underline focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40"
        >
          {value}
        </button>
      ) : (
        <span className="font-bold text-ink">—</span>
      )}
    </div>
  );
}

export function Settings({ onRepoChange }: { onRepoChange: () => void }) {
  const { notify } = useUi();
  const config = useAsync(() => api.loadConfig());
  const adapters = useAsync(() => api.adapters());

  const enabled = new Set<AgentId>(config.data?.enabledAdapters ?? []);
  const probePolicy = config.data?.liveProbePolicy;

  async function chooseRepo() {
    const res = await api.chooseRepo();
    if (!res.ok) {
      notify("error", res.error);
      return;
    }
    if (res.data) {
      notify("success", `Repo set to ${res.data}`);
      onRepoChange();
      config.reload();
      adapters.reload();
    }
  }

  async function verifySources() {
    const res = await api.verifySources();
    if (!res.ok) {
      notify("error", res.error);
      return;
    }
    notify(res.data.ok ? "success" : "info", res.data.ok ? "All sources verified" : "Some sources need a look");
  }

  async function toggleAdapter(id: AgentId) {
    const next = new Set(enabled);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    const res = await api.updateConfig({ enabledAdapters: [...next] });
    if (res.ok) {
      notify("success", "Adapters updated");
      config.reload();
    } else {
      notify("error", res.error);
    }
  }

  async function setProbe(policy: "off" | "safe") {
    const res = await api.updateConfig({ liveProbePolicy: policy });
    if (res.ok) {
      notify("success", `Probe policy → ${policy}`);
      config.reload();
    } else {
      notify("error", res.error);
    }
  }

  async function openFolder(target: string) {
    const res = await api.openPath(target);
    if (!res.ok) {
      notify("error", res.error);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-3xl font-black">Settings</h1>

      <div className="flex gap-3">
        <Button variant="blue" icon={Folder} onClick={chooseRepo}>
          Choose repo
        </Button>
        <Button variant="grape" icon={Search} onClick={verifySources}>
          Verify sources
        </Button>
      </div>

      <Panel>
        <h3 className="mb-3 text-lg font-black">Config</h3>
        {config.loading ? (
          <Spinner />
        ) : config.error ? (
          <span className="font-bold text-red">{config.error}</span>
        ) : (
          <div className="flex flex-col gap-2">
            <Row label="Transport mode" value={config.data?.transport.mode} />
            <PathRow label="Embedded repo" value={config.data?.transport.embeddedRepoPath} onOpen={openFolder} />
            <PathRow label="State dir" value={config.data?.stateDir} onOpen={openFolder} />
          </div>
        )}
      </Panel>

      <Panel>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-lg font-black">Live probe policy</h3>
          <div className="flex gap-2">
            {(["off", "safe"] as const).map((policy) => (
              <Button
                key={policy}
                variant={probePolicy === policy ? "blue" : "ghost"}
                onClick={() => setProbe(policy)}
              >
                {policy}
              </Button>
            ))}
          </div>
        </div>
        <p className="text-sm font-semibold text-ink-soft">
          “safe” lets doctor run read-only `--help` probes against installed agents; “off” skips them.
        </p>
      </Panel>

      <Panel>
        <h3 className="mb-3 text-lg font-black">Agents &amp; where skills land</h3>
        {adapters.loading ? (
          <Spinner />
        ) : (
          <div className="flex flex-col gap-2.5">
            {adapters.data?.map((adapter) => {
              const on = enabled.has(adapter.id);
              return (
                <div
                  key={adapter.id}
                  className="flex items-center gap-2.5 rounded-2xl border-2 border-ink/8 px-3 py-2"
                >
                  <span className="grid h-8 w-8 place-items-center rounded-xl border-2 border-blue-ring bg-blue/10 text-blue">
                    <Computer className="h-4 w-4" strokeWidth={2.2} />
                  </span>
                  <span className="font-extrabold">{adapter.label}</span>
                  <button
                    type="button"
                    title="Open in Finder"
                    onClick={() => openFolder(adapter.installDir)}
                    className="ml-auto truncate rounded text-xs font-semibold text-blue underline focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40"
                  >
                    {adapter.installDir}
                  </button>
                  <button
                    type="button"
                    aria-pressed={on}
                    title={on ? "Enabled — click to disable" : "Disabled — click to enable"}
                    onClick={() => toggleAdapter(adapter.id)}
                    className={cn(
                      "relative h-6 w-11 shrink-0 rounded-full border-2 transition-colors focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40",
                      on ? "border-mint-ring bg-mint" : "border-ink/15 bg-ink/10",
                    )}
                  >
                    <span
                      className={cn(
                        "absolute top-[2px] h-4 w-4 rounded-full border border-ink/10 bg-cloud transition-all",
                        on ? "left-[22px]" : "left-[2px]",
                      )}
                    />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}
