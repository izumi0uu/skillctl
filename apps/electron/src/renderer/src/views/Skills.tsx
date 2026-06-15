import { useEffect, useMemo, useState } from "react";
import { CloudUpload, EditPencil, FolderPlus, Lock } from "iconoir-react";

import { AdoptWizard } from "../components/AdoptWizard";
import { SkillReader } from "../components/SkillReader";
import { Badge, Button, cn, Panel, Spinner, Tile } from "../components/ui";
import { api, useAsync } from "../lib/api";

const CATEGORY_DOTS = ["bg-lemon", "bg-blue", "bg-mint", "bg-grape", "bg-pink", "bg-sky", "bg-red"];

export function Skills({
  focusCategory,
  onFocusHandled,
}: {
  focusCategory?: string | null;
  onFocusHandled?: () => void;
}) {
  const taxonomy = useAsync(() => api.taxonomy());
  const sources = useAsync(() => api.sources());
  const [selected, setSelected] = useState<string | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);

  const sourceMap = useMemo(() => {
    const map = new Map<string, NonNullable<typeof sources.data>["sources"][number]>();
    for (const entry of sources.data?.sources ?? []) {
      map.set(entry.skill_id, entry);
    }
    return map;
  }, [sources.data]);

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
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-black">Skills</h1>
        <Button variant="mint" icon={FolderPlus} onClick={() => setWizardOpen(true)}>
          Add skill
        </Button>
      </div>

      {taxonomy.data?.categories.map((category, i) => (
        <div key={category.id} id={`cat-${category.id}`} className="scroll-mt-4">
          <div className="mb-2.5 flex items-center gap-2.5">
            <span className={cn("h-5 w-5 rounded-lg", CATEGORY_DOTS[i % CATEGORY_DOTS.length])} />
            <h3 className="text-lg font-black">{category.label}</h3>
            <Badge tone="neutral">{category.skillCount}</Badge>
          </div>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-4">
            {category.skills.map((skill) => (
              <Tile
                key={skill.skill_id}
                accent="blue"
                selected={selected === skill.skill_id}
                onClick={() => setSelected(skill.skill_id)}
                className="p-3 pl-8 text-left"
              >
                <div className="truncate font-extrabold">{skill.skill_id}</div>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {skill.visibility === "private" && <Badge tone="lemon" icon={Lock}>private</Badge>}
                  {skill.local_modifications && <Badge tone="blue" icon={EditPencil}>modified</Badge>}
                  {skill.has_upstream && <Badge tone="neutral" icon={CloudUpload}>upstream</Badge>}
                </div>
              </Tile>
            ))}
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
        }}
      />
    </div>
  );
}
