import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { EditPencil, OpenInBrowser } from "iconoir-react";
import type { AgentId, CatalogSkill, SkillCategory, SkillMetaPatch, SourceRegistryEntry } from "@skillctl/core";

import { Badge, Button, cn, Spinner, useUi } from "./ui";
import { GhostLoader } from "./Loaders";
import { api } from "../lib/api";
import { sourceUrl } from "../../../shared/source-url";

const AGENTS: AgentId[] = ["claude-code", "codex", "pi", "hermes", "opencode"];
const CATEGORIES: SkillCategory[] = [
  "agent-infra",
  "knowledge-and-research",
  "frontend-and-design",
  "deployment-and-platform",
  "productivity-and-artifacts",
  "domain-aws-thrive",
  "system-and-demo",
];
const metaInputCls =
  "w-full rounded-2xl border-2 border-ink/15 bg-cloud px-3 py-2 text-sm font-semibold text-ink focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40";

interface MetaForm {
  targets: AgentId[];
  visibility: "public" | "private";
  category: SkillCategory | "";
  tags: string;
  portability: AgentId[];
}

function toggleAgent(list: AgentId[], agent: AgentId): AgentId[] {
  return list.includes(agent) ? list.filter((value) => value !== agent) : [...list, agent];
}

export function SkillReader({
  skillId,
  entry,
  skill,
  onClose,
  onSaved,
}: {
  skillId: string | null;
  entry?: SourceRegistryEntry;
  skill?: CatalogSkill;
  onClose: () => void;
  onSaved?: () => void;
}) {
  const { confirm, notify } = useUi();
  const [doc, setDoc] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installs, setInstalls] = useState<string[]>([]);
  const [editing, setEditing] = useState(false);
  const [meta, setMeta] = useState<MetaForm | null>(null);

  useEffect(() => {
    if (!skillId) {
      return;
    }
    let active = true;
    setLoading(true);
    setDoc(null);
    setError(null);
    api
      .readSkillDoc(skillId)
      .then((res) => {
        if (!active) return;
        if (res.ok) setDoc(res.data);
        else setError(res.error);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [skillId]);

  useEffect(() => {
    if (!skillId) {
      setInstalls([]);
      return;
    }
    let active = true;
    api.skillInstalls(skillId).then((res) => {
      if (active) setInstalls(res.ok ? res.data : []);
    });
    return () => {
      active = false;
    };
  }, [skillId]);

  useEffect(() => {
    setEditing(false);
    if (skill) {
      setMeta({
        targets: skill.targets,
        visibility: skill.visibility,
        category: skill.category ?? "",
        tags: (skill.tags ?? []).join(", "),
        portability: skill.distribution?.portability_allow_targets ?? [],
      });
    } else {
      setMeta(null);
    }
  }, [skill]);

  if (!skillId) {
    return null;
  }

  const url = sourceUrl(entry);

  async function openSource() {
    if (!url) {
      return;
    }
    const ok = await confirm({ title: "Open in browser?", body: url, confirmLabel: "Open ↗" });
    if (!ok) {
      return;
    }
    const res = await api.openExternal(url);
    if (!res.ok) {
      notify("error", res.error);
    }
  }

  async function saveMeta() {
    if (!skillId || !meta) {
      return;
    }
    const patch: SkillMetaPatch = {
      targets: meta.targets,
      visibility: meta.visibility,
      category: meta.category || undefined,
      tags: meta.tags.split(",").map((value) => value.trim()).filter(Boolean),
      portabilityAllowTargets: meta.portability,
    };
    const res = await api.setSkillMeta(skillId, patch);
    if (res.ok) {
      notify("success", "Metadata saved");
      setEditing(false);
      onSaved?.();
    } else {
      notify("error", res.error);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="flex h-[86vh] w-full max-w-3xl flex-col rounded-blob border-[3px] border-ink/10 bg-cloud shadow-puff animate-pop-in"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b-2 border-ink/8 px-6 py-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <GhostLoader mini />
              <h2 className="truncate text-xl font-black">{skillId}</h2>
            </div>
            {entry && (
              <div className="mt-1 flex flex-wrap gap-1.5">
                <Badge tone="blue">{entry.category_label}</Badge>
                <Badge tone="neutral">{entry.origin_kind}</Badge>
                {entry.visibility === "private" && <Badge tone="lemon">private</Badge>}
                {entry.local_modifications && <Badge tone="grape">modified</Badge>}
              </div>
            )}
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs font-bold text-ink-soft">
              installed:
              {installs.length > 0 ? (
                installs.map((agent) => (
                  <Badge key={agent} tone="mint">
                    {agent}
                  </Badge>
                ))
              ) : (
                <Badge tone="neutral">nowhere yet</Badge>
              )}
            </div>
          </div>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            {skill && (
              <Button
                variant={editing ? "blue" : "ghost"}
                icon={EditPencil}
                onClick={() => setEditing((value) => !value)}
              >
                Edit
              </Button>
            )}
            {url && (
              <Button variant="blue" icon={OpenInBrowser} onClick={openSource}>
                Source
              </Button>
            )}
            <Button variant="ghost" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-auto px-6 py-5">
          {editing && meta ? (
            <div className="flex flex-col gap-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold text-ink-soft">Targets</span>
                <div className="flex flex-wrap gap-2">
                  {AGENTS.map((agent) => (
                    <button
                      key={agent}
                      type="button"
                      onClick={() => setMeta({ ...meta, targets: toggleAgent(meta.targets, agent) })}
                      className={cn(
                        "rounded-full border-2 px-3 py-1 text-sm font-bold focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40",
                        meta.targets.includes(agent) ? "border-mint-ring bg-mint/15 text-ink" : "border-ink/15 text-ink-soft",
                      )}
                    >
                      {agent}
                    </button>
                  ))}
                </div>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold text-ink-soft">Visibility</span>
                <div className="flex gap-2">
                  {(["public", "private"] as const).map((value) => (
                    <Button
                      key={value}
                      variant={meta.visibility === value ? "blue" : "ghost"}
                      onClick={() => setMeta({ ...meta, visibility: value })}
                    >
                      {value}
                    </Button>
                  ))}
                </div>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold text-ink-soft">Category</span>
                <select
                  className={metaInputCls}
                  value={meta.category}
                  onChange={(event) => setMeta({ ...meta, category: event.target.value as SkillCategory | "" })}
                >
                  <option value="">(unset)</option>
                  {CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold text-ink-soft">Tags (comma-separated)</span>
                <input
                  className={metaInputCls}
                  value={meta.tags}
                  onChange={(event) => setMeta({ ...meta, tags: event.target.value })}
                />
              </label>
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-bold text-ink-soft">Portability override — allow targets</span>
                <div className="flex flex-wrap gap-2">
                  {AGENTS.map((agent) => (
                    <button
                      key={agent}
                      type="button"
                      onClick={() => setMeta({ ...meta, portability: toggleAgent(meta.portability, agent) })}
                      className={cn(
                        "rounded-full border-2 px-3 py-1 text-sm font-bold focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40",
                        meta.portability.includes(agent) ? "border-grape-ring bg-grape/15 text-ink" : "border-ink/15 text-ink-soft",
                      )}
                    >
                      {agent}
                    </button>
                  ))}
                </div>
              </label>
              <div className="flex justify-end gap-2">
                <Button variant="ghost" onClick={() => setEditing(false)}>
                  Cancel
                </Button>
                <Button variant="mint" onClick={saveMeta}>
                  Save metadata
                </Button>
              </div>
            </div>
          ) : loading ? (
            <div className="flex flex-col items-center gap-4 py-12">
              <Spinner />
              <p className="font-bold text-ink-soft">loading…</p>
            </div>
          ) : error ? (
            <p className="font-bold text-red">{error}</p>
          ) : (
            <div className="md-body">
              <Markdown remarkPlugins={[remarkGfm]}>{doc ?? ""}</Markdown>
            </div>
          )}
        </div>

        {entry && (
          <div className="flex flex-wrap gap-x-6 gap-y-1 border-t-2 border-ink/8 px-6 py-3 text-xs font-semibold text-ink-soft">
            {entry.upstream_repo && (
              <span>
                repo: <span className="text-ink">{entry.upstream_repo}</span>
              </span>
            )}
            {entry.ref && (
              <span>
                ref: <span className="text-ink">{entry.ref}</span>
              </span>
            )}
            <span>
              path: <span className="text-ink">{entry.canonical_rel_path}</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
