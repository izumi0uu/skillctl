import { useState, type ReactNode } from "react";
import { Folder } from "iconoir-react";
import type { AdoptSkillOptions } from "@skillctl/core";

import { Button, cn, useUi } from "./ui";
import { api } from "../lib/api";

type OriginKind = "local-authored" | "imported-upstream" | "derived-from-upstream";
type SourceType = "" | "github" | "git" | "local";
type Visibility = "public" | "private";

const ORIGINS: { value: OriginKind; label: string }[] = [
  { value: "local-authored", label: "Local" },
  { value: "imported-upstream", label: "Imported" },
  { value: "derived-from-upstream", label: "Derived" },
];

const inputClass =
  "w-full rounded-2xl border-2 border-ink/15 bg-cloud px-3 py-2 text-sm font-semibold text-ink focus:outline-none focus-visible:ring-4 focus-visible:ring-blue/40";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-bold text-ink-soft">{label}</span>
      {children}
    </label>
  );
}

export function AdoptWizard({ open, onClose, onAdopted }: { open: boolean; onClose: () => void; onAdopted: () => void }) {
  const { notify } = useUi();
  const [sourcePath, setSourcePath] = useState("");
  const [originKind, setOriginKind] = useState<OriginKind>("local-authored");
  const [visibility, setVisibility] = useState<Visibility>("public");
  const [destinationSubdir, setDestinationSubdir] = useState("");
  const [fromRepo, setFromRepo] = useState("");
  const [ref, setRef] = useState("");
  const [skillPath, setSkillPath] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("");
  const [localModifications, setLocalModifications] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (!open) {
    return null;
  }

  const isUpstream = originKind !== "local-authored";

  async function chooseFolder() {
    const res = await api.chooseDirectory();
    if (res.ok && res.data) {
      setSourcePath(res.data);
    } else if (!res.ok) {
      notify("error", res.error);
    }
  }

  async function submit() {
    if (!sourcePath) {
      notify("error", "Pick a skill folder first");
      return;
    }
    setSubmitting(true);
    const options: AdoptSkillOptions = {
      sourcePath,
      originKind,
      visibility,
      destinationSubdir: destinationSubdir || undefined,
      fromRepo: fromRepo || undefined,
      ref: ref || undefined,
      skillPath: skillPath || undefined,
      sourceUrl: sourceUrl || undefined,
      sourceType: sourceType || undefined,
      localModifications: localModifications || undefined,
    };
    const res = await api.adopt(options);
    setSubmitting(false);
    if (res.ok) {
      notify("success", `Adopted ${res.data.skill.skill_id}`);
      onAdopted();
      onClose();
    } else {
      notify("error", `Adopt flopped: ${res.error}`);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 p-4 backdrop-blur-sm">
      <div className="flex max-h-[88vh] w-full max-w-lg flex-col rounded-blob border-[3px] border-ink/10 bg-cloud shadow-puff animate-pop-in">
        <div className="border-b-2 border-ink/8 px-6 py-4">
          <h2 className="text-xl font-black">Add a skill</h2>
          <p className="text-sm font-semibold text-ink-soft">Copy a skill folder into this repo and register it.</p>
        </div>

        <div className="flex flex-col gap-4 overflow-auto px-6 py-4">
          <Field label="Skill folder (must contain SKILL.md)">
            <div className="flex items-center gap-2">
              <Button variant="blue" icon={Folder} onClick={chooseFolder}>
                Choose folder
              </Button>
              <span className="truncate text-sm font-bold text-ink/70">{sourcePath || "no folder chosen"}</span>
            </div>
          </Field>

          <Field label="Origin">
            <div className="flex gap-2">
              {ORIGINS.map((o) => (
                <Button key={o.value} variant={originKind === o.value ? "blue" : "ghost"} onClick={() => setOriginKind(o.value)}>
                  {o.label}
                </Button>
              ))}
            </div>
          </Field>

          <Field label="Visibility">
            <div className="flex gap-2">
              {(["public", "private"] as const).map((v) => (
                <Button key={v} variant={visibility === v ? "blue" : "ghost"} onClick={() => setVisibility(v)}>
                  {v}
                </Button>
              ))}
            </div>
          </Field>

          <Field label="Destination subdir (optional, e.g. frontend-and-design/foo)">
            <input className={inputClass} value={destinationSubdir} onChange={(e) => setDestinationSubdir(e.target.value)} placeholder="defaults to skills/" />
          </Field>

          {isUpstream && (
            <div className="flex flex-col gap-4 rounded-2xl border-2 border-ink/8 p-3">
              <Field label="Upstream repo">
                <input className={inputClass} value={fromRepo} onChange={(e) => setFromRepo(e.target.value)} placeholder="owner/repo" />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Ref">
                  <input className={inputClass} value={ref} onChange={(e) => setRef(e.target.value)} placeholder="main" />
                </Field>
                <Field label="Source type">
                  <select className={inputClass} value={sourceType} onChange={(e) => setSourceType(e.target.value as SourceType)}>
                    <option value="">—</option>
                    <option value="github">github</option>
                    <option value="git">git</option>
                    <option value="local">local</option>
                  </select>
                </Field>
              </div>
              <Field label="Skill path in upstream">
                <input className={inputClass} value={skillPath} onChange={(e) => setSkillPath(e.target.value)} placeholder="skills/foo" />
              </Field>
              <Field label="Source URL">
                <input className={inputClass} value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} placeholder="https://…" />
              </Field>
              <label className="flex items-center gap-2 text-sm font-bold">
                <input type="checkbox" checked={localModifications} onChange={(e) => setLocalModifications(e.target.checked)} className="h-4 w-4 accent-blue" />
                Has local modifications
              </label>
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 border-t-2 border-ink/8 px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="mint" onClick={submit} disabled={submitting || !sourcePath}>
            {submitting ? "Adding…" : "Add skill"}
          </Button>
        </div>
      </div>
    </div>
  );
}
