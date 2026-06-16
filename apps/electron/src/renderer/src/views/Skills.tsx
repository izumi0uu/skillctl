import { useEffect, useMemo, useState } from "react";
import { CloudUpload, EditPencil, FolderPlus, Lock, Refresh } from "iconoir-react";

import { AdoptWizard } from "../components/AdoptWizard";
import { SkillReader } from "../components/SkillReader";
import { Badge, Button, cn, Panel, Spinner, useUi } from "../components/ui";
import { applyToggle } from "../../../shared/staged-toggles";
import { api, useAsync } from "../lib/api";

type SyncResultData = Extract<Awaited<ReturnType<typeof api.sync>>, { ok: true }>["data"];

const CATEGORY_DOTS = ["bg-lemon", "bg-blue", "bg-mint", "bg-grape", "bg-pink", "bg-sky", "bg-red"];

function Switch({ on, onToggle, title }: { on: boolean; onToggle: () => void; title: string }) {
  return (
    <button
      type="button"
      title={title}
      aria-pressed={on}
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
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
  );
}

export function Skills({ focusCategory, onFocusHandled }: { focusCategory?: string | null; onFocusHandled?: () => void }) {
  const { notify } = useUi();
  const taxonomy = useAsync(() => api.taxonomy());
  const sources = useAsync(() => api.sources());
  const catalog = useAsync(() => api.loadCatalog());
  const [selected, setSelected] = useState<string | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  // Staged toggles live ONLY in this page: skillId -> desired enabled. Leaving
  // the page (or quitting) drops them; nothing is written until "Sync now".
  const [pending, setPending] = useState<Map<string, boolean>>(new Map());
  const [syncing, setSyncing] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "on" | "off">("all");
  const [lastSync, setLastSync] = useState<SyncResultData | null>(null);

  const sourceMap = useMemo(() => {
    const map = new Map<string, NonNullable<typeof sources.data>["sources"][number]>();
    for (const entry of sources.data?.sources ?? []) {
      map.set(entry.skill_id, entry);
    }
    return map;
  }, [sources.data]);

  const enabledMap = useMemo(() => {
    const map = new Map<string, boolean>();
    for (const skill of catalog.data?.skills ?? []) {
      map.set(skill.skill_id, skill.enabled !== false);
    }
    return map;
  }, [catalog.data]);

  useEffect(() => {
    if (!focusCategory || !taxonomy.data) {
      return;
    }
    const el = document.getElementById(`cat-${focusCategory}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      onFocusHandled?.();
    }
  }, [focusCategory, taxonomy.data, onFocusHandled]);

  function displayedOn(skillId: string): boolean {
    return pending.has(skillId) ? pending.get(skillId)! : (enabledMap.get(skillId) ?? true);
  }

  function toggle(skillId: string) {
    const actual = enabledMap.get(skillId) ?? true;
    setPending((prev) => applyToggle(prev, skillId, displayedOn(skillId), actual));
  }

  async function syncNow() {
    setSyncing(true);
    try {
      for (const [skillId, enabled] of pending) {
        const res = await api.setSkillEnabled(skillId, enabled);
        if (!res.ok) {
          notify("error", `Could not stage ${skillId}: ${res.error}`);
          return;
        }
      }
      const result = await api.sync();
      if (result.ok) {
        notify("success", `Synced — ${pending.size} change(s) applied`);
        setLastSync(result.data);
        setPending(new Map());
        catalog.reload();
        taxonomy.reload();
        sources.reload();
      } else {
        notify("error", `Sync failed: ${result.error}`);
        catalog.reload();
      }
    } finally {
      setSyncing(false);
    }
  }

  if (taxonomy.loading) {
    return <Spinner />;
  }
  if (taxonomy.error) {
    return (
      <Panel>
        <span className="font-bold text-red">{taxonomy.error}</span>
      </Panel>
    );
  }

  const q = query.trim().toLowerCase();
  const filteredCategories = (taxonomy.data?.categories ?? [])
    .map((category) => ({
      category,
      skills: category.skills.filter((skill) => {
        if (q && !skill.skill_id.toLowerCase().includes(q)) return false;
        if (filter === "on" && !displayedOn(skill.skill_id)) return false;
        if (filter === "off" && displayedOn(skill.skill_id)) return false;
        return true;
      }),
    }))
    .filter((entry) => entry.skills.length > 0);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-3xl font-black">Skills</h1>
        <div className="flex items-center gap-2">
          {pending.size > 0 && (
            <Button variant="blue" icon={Refresh} onClick={syncNow} disabled={syncing}>
              {syncing ? "Syncing…" : "Sync now"}
            </Button>
          )}
          <Button variant="mint" icon={FolderPlus} onClick={() => setWizardOpen(true)}>
            Add skill
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search skills…"
          className="w-56 rounded-full border-2 border-ink/15 bg-cloud px-4 py-2 text-sm font-semibold text-ink focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40"
        />
        {(["all", "on", "off"] as const).map((option) => (
          <Button key={option} variant={filter === option ? "blue" : "ghost"} onClick={() => setFilter(option)}>
            {option === "all" ? "All" : option === "on" ? "Enabled" : "Disabled"}
          </Button>
        ))}
      </div>

      {lastSync && (
        <Panel>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-lg font-black">Last sync</h3>
            <button
              type="button"
              onClick={() => setLastSync(null)}
              className="rounded text-sm font-bold text-ink-soft underline focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40"
            >
              dismiss
            </button>
          </div>
          <div className="mb-2 flex flex-wrap gap-2">
            <Badge tone="mint">{lastSync.copied.length} copied</Badge>
            {lastSync.skipped.length > 0 && <Badge tone="lemon">{lastSync.skipped.length} skipped</Badge>}
          </div>
          {lastSync.skipped.length > 0 && (
            <ul className="flex max-h-40 flex-col gap-1 overflow-auto text-sm">
              {lastSync.skipped.map((entry, index) => (
                <li key={`${entry.agent}-${entry.skillId}-${index}`} className="flex items-center gap-2">
                  <Badge tone="neutral">{entry.agent}</Badge>
                  <span className="font-bold">{entry.skillId}</span>
                  <span className="truncate text-xs font-semibold text-ink-soft">{entry.reason}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      )}

      {filteredCategories.length === 0 && (
        <Panel>
          <p className="font-bold text-ink-soft">No skills match your search.</p>
        </Panel>
      )}

      {filteredCategories.map(({ category, skills }, i) => (
        <div key={category.id} id={`cat-${category.id}`} className="scroll-mt-4">
          <div className="mb-2.5 flex items-center gap-2.5">
            <span className={cn("h-5 w-5 rounded-lg", CATEGORY_DOTS[i % CATEGORY_DOTS.length])} />
            <h3 className="text-lg font-black">{category.label}</h3>
            <Badge tone="neutral">{skills.length}</Badge>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
            {skills.map((skill) => {
              const on = displayedOn(skill.skill_id);
              const staged = pending.has(skill.skill_id);
              return (
                <div
                  key={skill.skill_id}
                  className={cn(
                    "group relative rounded-chunk border-[3px] bg-cloud p-3 pr-14 shadow-puff-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-puff",
                    staged ? "border-lemon-ring" : "border-ink/10",
                    !on && "opacity-60",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => setSelected(skill.skill_id)}
                    className="block w-full rounded text-left focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40"
                  >
                    <div className="truncate font-extrabold">{skill.skill_id}</div>
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {skill.visibility === "private" && <Badge tone="lemon" icon={Lock}>private</Badge>}
                      {skill.local_modifications && <Badge tone="blue" icon={EditPencil}>modified</Badge>}
                      {skill.has_upstream && <Badge tone="neutral" icon={CloudUpload}>upstream</Badge>}
                      {!on && <Badge tone="red">off</Badge>}
                      {staged && <Badge tone="lemon">staged</Badge>}
                    </div>
                  </button>
                  <div className="absolute right-3 top-3">
                    <Switch
                      on={on}
                      onToggle={() => toggle(skill.skill_id)}
                      title={on ? "Enabled — click to disable" : "Disabled — click to enable"}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <SkillReader
        skillId={selected}
        entry={selected ? sourceMap.get(selected) : undefined}
        onClose={() => setSelected(null)}
      />
      <AdoptWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onAdopted={() => {
          taxonomy.reload();
          sources.reload();
          catalog.reload();
        }}
      />
    </div>
  );
}
