import { useState } from "react";
import { Computer, Folder, Search } from "iconoir-react";
import type { AgentId } from "@skillctl/core";

import { Badge, Button, cn, Panel, Row, Spinner, useUi } from "../components/ui";
import { api, useAsync } from "../lib/api";

type VerifyReport = Extract<Awaited<ReturnType<typeof api.verifySources>>, { ok: true }>["data"];
type VerifyStatus = VerifyReport["results"][number]["status"];

function verifyTone(status: VerifyStatus): "mint" | "lemon" | "red" | "neutral" {
  if (status === "ok") return "mint";
  if (status === "warn") return "lemon";
  if (status === "error") return "red";
  return "neutral";
}

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
  const publishable = useAsync(() => api.publish());
  const [verify, setVerify] = useState<{ loading: boolean; report: VerifyReport | null }>({
    loading: false,
    report: null,
  });
  const verifyReport = verify.report;

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
    setVerify({ loading: true, report: null });
    const res = await api.verifySources();
    if (!res.ok) {
      setVerify({ loading: false, report: null });
      notify("error", res.error);
      return;
    }
    setVerify({ loading: false, report: res.data });
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
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-lg font-black">Source verification</h3>
          <Button variant="grape" icon={Search} onClick={verifySources} disabled={verify.loading}>
            {verify.loading ? "Verifying…" : "Verify sources"}
          </Button>
        </div>
        {verify.loading ? (
          <div className="flex items-center gap-2 text-sm font-bold text-ink-soft">
            <Spinner /> checking upstream refs…
          </div>
        ) : verifyReport ? (
          <div className="flex flex-col gap-2.5">
            <div className="flex flex-wrap gap-2">
              <Badge tone={verifyReport.ok ? "mint" : "lemon"}>
                {verifyReport.ok ? "all good" : "needs attention"}
              </Badge>
              {(["ok", "warn", "error", "skip"] as const).map((status) => {
                const count = verifyReport.results.filter((entry) => entry.status === status).length;
                return count > 0 ? (
                  <Badge key={status} tone={verifyTone(status)}>
                    {count} {status}
                  </Badge>
                ) : null;
              })}
            </div>
            <div className="flex max-h-80 flex-col gap-1.5 overflow-auto">
              {verifyReport.results.map((entry) => (
                <div key={entry.skill_id} className="flex items-start gap-2 rounded-2xl border-2 border-ink/8 p-2 text-sm">
                  <Badge tone={verifyTone(entry.status)}>{entry.status}</Badge>
                  <div className="min-w-0">
                    <span className="font-extrabold">{entry.skill_id}</span>
                    <span className="font-semibold text-ink-soft"> — {entry.detail}</span>
                    {entry.resolved_ref && (
                      <span className="ml-1 text-xs font-semibold text-ink-soft">({entry.resolved_ref})</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm font-semibold text-ink-soft">
            Check that each upstream skill still resolves to its pinned ref. This hits the network.
          </p>
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

      <Panel>
        <h3 className="mb-3 text-lg font-black">Publishable skills · {publishable.data?.length ?? 0}</h3>
        {publishable.loading ? (
          <Spinner />
        ) : (
          <div className="flex max-h-72 flex-col gap-1.5 overflow-auto text-sm">
            {publishable.data?.map((skill) => (
              <div key={skill.skill_id} className="flex items-center gap-2">
                <Badge tone="mint">{skill.origin_kind}</Badge>
                <span className="font-bold">{skill.skill_id}</span>
                <span className="ml-auto truncate text-xs font-semibold text-ink-soft">
                  {skill.canonical_rel_path}
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
