import { useState, type ReactNode } from "react";
import { CheckCircle, CloudUpload, Compass, Globe, Lock, Packages, Rocket, Tools, Trash, WarningTriangle } from "iconoir-react";

import type { DiffChange, IpcResult, SkillConflictLite } from "../../../shared/ipc-contract";
import { Badge, Button, type IconType, Panel, Spinner, useUi } from "../components/ui";
import { TransportFlow } from "../components/TransportFlow";
import { api, useAsync } from "../lib/api";

type MutatingKey = "discover" | "sync" | "repair" | "prune" | "bootstrap";
type ButtonVariant = "blue" | "mint" | "grape" | "lemon" | "red";

interface ActionDef {
  key: MutatingKey;
  label: string;
  icon: IconType;
  variant: ButtonVariant;
  danger: boolean;
  body: string;
}

const ACTIONS: ActionDef[] = [
  { key: "discover", label: "Discover", icon: Compass, variant: "blue", danger: false, body: "Re-scan source roots and rewrite skillctl.catalog.json." },
  { key: "repair", label: "Repair", icon: Tools, variant: "grape", danger: false, body: "Re-sync managed skills and re-run doctor to clear drift." },
  { key: "prune", label: "Prune", icon: Trash, variant: "red", danger: true, body: "Remove skillctl-managed skills from agent directories. Unmanaged skills are left alone." },
  { key: "bootstrap", label: "Bootstrap", icon: Rocket, variant: "lemon", danger: false, body: "Install deps and build the embedded vercel-skills CLI. This can take a while." },
];

const ACTION_API: Record<MutatingKey, () => Promise<IpcResult<unknown>>> = {
  discover: api.discover,
  sync: api.sync,
  repair: api.repair,
  prune: api.prune,
  bootstrap: api.bootstrap,
};

const STATS: { key: "managedSkills" | "publicSkills" | "privateSkills" | "upstreamSkills"; label: string; icon: IconType; chip: string }[] = [
  { key: "managedSkills", label: "Managed", icon: Packages, chip: "bg-blue/12 text-blue border-blue-ring" },
  { key: "publicSkills", label: "Public", icon: Globe, chip: "bg-mint/15 text-mint border-mint-ring" },
  { key: "privateSkills", label: "Private", icon: Lock, chip: "bg-grape/14 text-grape border-grape-ring" },
  { key: "upstreamSkills", label: "Upstream", icon: CloudUpload, chip: "bg-sky/14 text-sky border-sky-ring" },
];

function DiffSummary({ changes, conflicts }: { changes: DiffChange[]; conflicts: SkillConflictLite[] }) {
  if (changes.length === 0 && conflicts.length === 0) {
    return <p className="font-bold text-ink-soft">Catalog is up to date — nothing pending.</p>;
  }
  const added = changes.filter((c) => c.kind === "added").length;
  const changed = changes.filter((c) => c.kind === "changed").length;
  const removed = changes.filter((c) => c.kind === "removed").length;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <Badge tone="mint">+{added} added</Badge>
        <Badge tone="lemon">~{changed} changed</Badge>
        <Badge tone="red">−{removed} removed</Badge>
        {conflicts.length > 0 && <Badge tone="red">{conflicts.length} conflicts</Badge>}
      </div>
      {changes.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {changes.slice(0, 12).map((c) => (
            <li key={`${c.kind}-${c.skill}`} className="flex items-center gap-2">
              <Badge tone={c.kind === "added" ? "mint" : c.kind === "removed" ? "red" : "lemon"}>{c.kind}</Badge>
              <span className="truncate font-semibold text-ink/75">{c.skill}</span>
            </li>
          ))}
          {changes.length > 12 && (
            <li className="text-xs font-bold text-ink-soft">+{changes.length - 12} more…</li>
          )}
        </ul>
      )}
    </div>
  );
}

export function Dashboard({ onNavigate }: { onNavigate: (category: string) => void }) {
  const { confirm, notify } = useUi();
  const summary = useAsync(() => api.summary());
  const taxonomy = useAsync(() => api.taxonomy());
  const doctor = useAsync(() => api.doctor());
  const diff = useAsync(() => api.diff());
  const [running, setRunning] = useState<MutatingKey | null>(null);

  async function runAction(action: ActionDef) {
    let preview: ReactNode;
    if (action.key === "discover") {
      const pending = await api.diff();
      if (pending.ok) {
        preview = <DiffSummary changes={pending.data.changes} conflicts={pending.data.conflicts} />;
      }
    }
    const ok = await confirm({
      title: `${action.label}?`,
      body: action.body,
      confirmLabel: `${action.label}!`,
      danger: action.danger,
      preview,
    });
    if (!ok) {
      return;
    }
    setRunning(action.key);
    const res = await ACTION_API[action.key]();
    setRunning(null);
    if (res.ok) {
      notify("success", `${action.label} done!`);
      summary.reload();
      taxonomy.reload();
      doctor.reload();
      diff.reload();
    } else {
      notify("error", `${action.label} flopped: ${res.error}`);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl font-black">Howdy 👋</h1>

      <section className="grid grid-cols-4 gap-4">
        {STATS.map((stat) => {
          const Icon = stat.icon;
          return (
            <Panel key={stat.key} hover className="animate-pop-in">
              <span className={`grid h-11 w-11 place-items-center rounded-2xl border-2 ${stat.chip}`}>
                <Icon className="h-6 w-6" strokeWidth={2.2} />
              </span>
              <div className="mt-3 text-4xl font-black tabular-nums leading-none">
                {summary.loading ? "··" : (summary.data?.[stat.key] ?? 0)}
              </div>
              <div className="mt-1 text-sm font-bold text-ink-soft">{stat.label}</div>
            </Panel>
          );
        })}
      </section>

      <TransportFlow
        onSynced={() => {
          summary.reload();
          taxonomy.reload();
          doctor.reload();
        }}
      />

      <section className="grid grid-cols-3 gap-4">
        <Panel className="col-span-2">
          <h2 className="mb-1 text-lg font-black">What do you want to do?</h2>
          <p className="mb-4 text-sm font-semibold text-ink-soft">Bootstrap spawns pnpm/node — it takes a beat.</p>
          <div className="flex flex-wrap gap-3">
            {ACTIONS.map((action) => (
              <Button
                key={action.key}
                variant={action.variant}
                icon={action.icon}
                disabled={running !== null}
                onClick={() => runAction(action)}
              >
                {running === action.key ? "Running…" : action.label}
              </Button>
            ))}
          </div>
        </Panel>

        <Panel hover>
          <h2 className="mb-3 text-lg font-black">Health</h2>
          {doctor.loading ? (
            <Spinner />
          ) : doctor.error ? (
            <Badge tone="red" icon={WarningTriangle}>error</Badge>
          ) : (
            <div className="flex flex-col items-start gap-3">
              <span
                className={`grid h-14 w-14 place-items-center rounded-full border-[3px] ${
                  doctor.data?.healthy ? "border-mint-ring bg-mint/12 text-mint" : "border-lemon-ring bg-lemon/15 text-lemon"
                }`}
              >
                {doctor.data?.healthy ? (
                  <CheckCircle className="h-7 w-7" strokeWidth={2.2} />
                ) : (
                  <WarningTriangle className="h-7 w-7" strokeWidth={2.2} />
                )}
              </span>
              {doctor.data?.healthy ? <Badge tone="mint">healthy</Badge> : <Badge tone="lemon">needs love</Badge>}
              <div className="text-sm font-bold text-ink-soft">
                {doctor.data?.issues.length ?? 0} issues · {doctor.data?.portability.length ?? 0} portability
              </div>
            </div>
          )}
        </Panel>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-black">Pending changes</h2>
          <Button variant="ghost" onClick={() => diff.reload()}>
            Refresh
          </Button>
        </div>
        <Panel>
          {diff.loading ? (
            <Spinner />
          ) : diff.error ? (
            <span className="font-bold text-red">{diff.error}</span>
          ) : diff.data ? (
            <DiffSummary changes={diff.data.changes} conflicts={diff.data.conflicts} />
          ) : null}
        </Panel>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-black">Taxonomy</h2>
        {taxonomy.loading ? (
          <Spinner />
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
            {taxonomy.data?.categories.map((category) => (
              <button
                key={category.id}
                type="button"
                onClick={() => onNavigate(category.id)}
                className="flex items-center justify-between rounded-blob border-[3px] border-ink/10 bg-cloud p-5 shadow-puff transition-transform duration-200 hover:-translate-y-1 focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40"
              >
                <span className="font-bold text-ink/80">{category.label}</span>
                <Badge tone="blue">{category.skillCount}</Badge>
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
