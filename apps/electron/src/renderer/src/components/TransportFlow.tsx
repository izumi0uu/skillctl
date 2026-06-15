import { Fragment, useEffect, useMemo, useState } from "react";
import { Check, Codepen, Computer, Folder, Packages, Refresh } from "iconoir-react";

import type { ProgressEvent } from "../../../shared/ipc-contract";
import { Badge, Button, cn, type IconType, Panel, useUi } from "./ui";
import { api, useAsync } from "../lib/api";

type SyncData = Extract<Awaited<ReturnType<typeof api.sync>>, { ok: true }>["data"];
type Status = "idle" | "running" | "done" | "error";

const NODES: { key: string; label: string; icon: IconType }[] = [
  { key: "catalog", label: "Catalog", icon: Packages },
  { key: "cli", label: "vercel-skills", icon: Codepen },
  { key: "shared", label: "~/.agents/skills", icon: Folder },
  { key: "agents", label: "Agent dirs", icon: Computer },
];

// Maps a core sync stage to how far the pipeline has lit up (node index).
const STAGE_REACH: Record<string, number> = {
  transport: 1,
  start: 1,
  agent: 1,
  skill: 2,
  mirror: 3,
  attribution: 3,
  done: 4,
};

export function TransportFlow({ onSynced }: { onSynced?: () => void }) {
  const { confirm, notify } = useUi();
  const adapters = useAsync(() => api.adapters());
  const [status, setStatus] = useState<Status>("idle");
  const [litUpTo, setLitUpTo] = useState(0);
  const [progress, setProgress] = useState<{ current: number; total: number }>({ current: 0, total: 0 });
  const [result, setResult] = useState<SyncData | null>(null);

  useEffect(() => {
    return api.onProgress((event: ProgressEvent) => {
      if (event.op !== "sync" || event.phase !== "step") {
        return;
      }
      const reach = STAGE_REACH[event.stage ?? ""] ?? 0;
      setLitUpTo((prev) => Math.max(prev, reach));
      if (typeof event.current === "number" || typeof event.total === "number") {
        setProgress((p) => ({ current: event.current ?? p.current, total: event.total ?? p.total }));
      }
    });
  }, []);

  async function runSync() {
    const ok = await confirm({
      title: "Sync?",
      body: "Install managed skills into every enabled agent directory via the upstream CLI.",
      confirmLabel: "Sync!",
    });
    if (!ok) {
      return;
    }
    setStatus("running");
    setLitUpTo(0);
    setProgress({ current: 0, total: 0 });
    setResult(null);
    const res = await api.sync();
    if (res.ok) {
      setResult(res.data);
      setLitUpTo(NODES.length);
      setStatus("done");
      notify("success", `Synced ${res.data.copied.length} skill installs`);
      onSynced?.();
    } else {
      setStatus("error");
      notify("error", `Sync flopped: ${res.error}`);
    }
  }

  const copiedByAgent = useMemo(() => {
    const map = new Map<string, number>();
    for (const entry of result?.copied ?? []) {
      map.set(entry.agent, (map.get(entry.agent) ?? 0) + 1);
    }
    return map;
  }, [result]);

  const pct =
    progress.total > 0
      ? Math.min(100, Math.round((progress.current / progress.total) * 100))
      : status === "done"
        ? 100
        : 0;

  return (
    <Panel>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-black">Sync pipeline</h2>
          <p className="text-sm font-semibold text-ink-soft">
            catalog → vercel-skills CLI → ~/.agents/skills → agent dirs
          </p>
        </div>
        <Button variant="mint" icon={Refresh} onClick={runSync} disabled={status === "running"}>
          {status === "running" ? "Syncing…" : "Run Sync"}
        </Button>
      </div>

      <div className="flex items-center gap-1">
        {NODES.map((node, i) => {
          const nodeState =
            status === "done" || i < litUpTo
              ? "done"
              : i === litUpTo && status === "running"
                ? "active"
                : "idle";
          const Icon = node.icon;
          const passed = status === "done" || litUpTo > i + 1;
          const flowing = status === "running" && litUpTo === i + 1;
          return (
            <Fragment key={node.key}>
              <div
                className={cn(
                  "flex flex-1 flex-col items-center gap-1.5 rounded-chunk border-[3px] p-3 text-center transition-all duration-300",
                  nodeState === "done" && "border-mint-ring bg-mint/10",
                  nodeState === "active" && "border-blue-ring bg-blue/10 animate-pop-in",
                  nodeState === "idle" && "border-ink/10 bg-cloud opacity-60",
                )}
              >
                <span
                  className={cn(
                    "grid h-10 w-10 place-items-center rounded-2xl border-2",
                    nodeState === "done" && "border-mint-ring bg-mint/15 text-mint",
                    nodeState === "active" && "border-blue-ring bg-blue/15 text-blue",
                    nodeState === "idle" && "border-ink/10 text-ink-soft",
                  )}
                >
                  {nodeState === "done" ? (
                    <Check className="h-5 w-5" strokeWidth={2.4} />
                  ) : (
                    <Icon className="h-5 w-5" strokeWidth={2.2} />
                  )}
                </span>
                <span className="text-xs font-bold leading-tight">{node.label}</span>
              </div>
              {i < NODES.length - 1 && (
                <div
                  className={cn(
                    "h-1.5 w-6 shrink-0 rounded-full transition-colors",
                    passed ? "bg-mint" : flowing ? "animate-flow" : "bg-ink/10",
                  )}
                  style={
                    flowing
                      ? {
                          backgroundImage: "repeating-linear-gradient(90deg,#4C8DFF 0 9px,transparent 9px 18px)",
                          backgroundSize: "18px 100%",
                        }
                      : undefined
                  }
                />
              )}
            </Fragment>
          );
        })}
      </div>

      {(status === "running" || status === "done") && (
        <div className="mt-4">
          <div className="mb-1 flex justify-between text-xs font-bold text-ink-soft">
            <span>{status === "done" ? "Done" : "Copying skills…"}</span>
            <span className="tabular-nums">{progress.total > 0 ? `${progress.current}/${progress.total}` : ""}</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full border-2 border-ink/10 bg-ink/5">
            <div
              className={cn("h-full rounded-full transition-all duration-300", status === "done" ? "bg-mint" : "bg-blue")}
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      {status === "done" && result && (
        <div className="mt-4 flex flex-wrap gap-2">
          {adapters.data?.map((adapter) => {
            const count = copiedByAgent.get(adapter.id) ?? 0;
            return (
              <Badge key={adapter.id} tone={count > 0 ? "mint" : "neutral"}>
                {adapter.label}: {count}
              </Badge>
            );
          })}
          {result.skipped.length > 0 && <Badge tone="lemon">{result.skipped.length} skipped</Badge>}
        </div>
      )}
    </Panel>
  );
}
