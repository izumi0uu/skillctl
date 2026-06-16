import { useEffect, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { OpenInBrowser } from "iconoir-react";
import type { SourceRegistryEntry } from "@skillctl/core";

import { Badge, Button, Spinner, useUi } from "./ui";
import { GhostLoader } from "./Loaders";
import { api } from "../lib/api";
import { sourceUrl } from "../../../shared/source-url";

export function SkillReader({
  skillId,
  entry,
  onClose,
}: {
  skillId: string | null;
  entry?: SourceRegistryEntry;
  onClose: () => void;
}) {
  const { confirm, notify } = useUi();
  const [doc, setDoc] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [installs, setInstalls] = useState<string[]>([]);

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
          {loading ? (
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
