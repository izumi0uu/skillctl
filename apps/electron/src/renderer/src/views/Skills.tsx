import { useEffect, useMemo, useState } from "react";
import { CloudUpload, EditPencil, FolderPlus, Lock, Refresh, WarningTriangle } from "iconoir-react";

import { AdoptWizard } from "../components/AdoptWizard";
import { SkillReader } from "../components/SkillReader";
import { Badge, Button, cn, Panel, Spinner, useUi } from "../components/ui";
import { api, useAsync } from "../lib/api";

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
    const next = !displayedOn(skillId);
    setPending((prev) => {
      const map = new Map(prev);
      if (next === actual) {
        map.delete(skillId); // back to the saved state -> no longer a pending change
      } else {
        map.set(skillId, next);
      }
      return map;
    });
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

      {pending.size > 0 && (
        <div className="flex items-center gap-2.5 rounded-2xl border-[3px] border-lemon-ring bg-lemon/20 px-4 py-2.5 text-sm font-bold text-ink">
          <WarningTriangle className="h-5 w-5 shrink-0" strokeWidth={2.2} />
          <span>
            {pending.size} change{pending.size > 1 ? "s" : ""} staged on this page only — hit “Sync now” to apply them. Leaving
            this page discards them.
          </span>
        </div>
      )}

      {taxonomy.data?.categories.map((category, i) => (
        <div key={category.id} id={`cat-${category.id}`} className="scroll-mt-4">
          <div className="mb-2.5 flex items-center gap-2.5">
            <span className={cn("h-5 w-5 rounded-lg", CATEGORY_DOTS[i % CATEGORY_DOTS.length])} />
            <h3 className="text-lg font-black">{category.label}</h3>
            <Badge tone="neutral">{category.skillCount}</Badge>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
            {category.skills.map((skill) => {
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
