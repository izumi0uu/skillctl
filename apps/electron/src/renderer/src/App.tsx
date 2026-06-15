import { useEffect, useState } from "react";
import { Folder, Healthcare, Home, Puzzle, Settings } from "iconoir-react";

import type { ProgressEvent } from "../../shared/ipc-contract";
import { CoffeeLoader } from "./components/Loaders";
import { type IconType, Spinner, Tile } from "./components/ui";
import { api, useAsync } from "./lib/api";
import { Dashboard } from "./views/Dashboard";
import { Health } from "./views/Health";
import { Settings as SettingsView } from "./views/Settings";
import { Skills } from "./views/Skills";

type ViewId = "dashboard" | "skills" | "health" | "settings";
type NavAccent = "lemon" | "blue" | "mint" | "grape";

const NAV: { id: ViewId; label: string; icon: IconType; accent: NavAccent }[] = [
  { id: "dashboard", label: "Dashboard", icon: Home, accent: "lemon" },
  { id: "skills", label: "Skills", icon: Puzzle, accent: "blue" },
  { id: "health", label: "Health", icon: Healthcare, accent: "mint" },
  { id: "settings", label: "Settings", icon: Settings, accent: "grape" },
];

export function App() {
  const [view, setView] = useState<ViewId>("dashboard");
  const [running, setRunning] = useState<string | null>(null);
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null);
  const [skillsFocus, setSkillsFocus] = useState<string | null>(null);
  const repoRoot = useAsync(() => api.repoRoot());

  useEffect(() => {
    return api.onProgress((event: ProgressEvent) => {
      if (event.phase === "started") {
        setRunning(event.op);
        setProgress({ current: 0, total: 0 });
      } else if (event.phase === "step") {
        setProgress((p) => ({
          current: event.current ?? p?.current ?? 0,
          total: event.total ?? p?.total ?? 0,
        }));
      } else {
        setRunning(null);
        setProgress(null);
      }
    });
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden text-ink">
      <aside className="flex w-60 flex-col border-r-[3px] border-ink/10 bg-cloud/70">
        <div className="flex items-center gap-2.5 px-5 pb-5 pt-7">
          <span className="grid h-11 w-11 place-items-center rounded-2xl border-[3px] border-lemon-ring bg-lemon text-ink shadow-puff-sm animate-float">
            <Puzzle className="h-6 w-6" strokeWidth={2.4} />
          </span>
          <div>
            <div className="text-xl font-black leading-none">skillctl</div>
            <div className="text-xs font-bold text-ink-soft">control panel</div>
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-2 px-3">
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <Tile
                key={item.id}
                accent={item.accent}
                selected={view === item.id}
                onClick={() => setView(item.id)}
                className="w-full px-3.5 py-2.5 text-left"
              >
                <span className="flex items-center gap-2.5 pl-5 text-sm font-extrabold">
                  <Icon className="h-5 w-5" strokeWidth={2.2} />
                  {item.label}
                </span>
              </Tile>
            );
          })}
        </nav>

        <div className="px-4 py-4">
          {running ? (
            <span className="inline-flex items-center gap-2 rounded-full border-[3px] border-blue-ring bg-blue/10 px-3 py-2 text-xs font-extrabold text-ink">
              <Spinner /> {running}…
            </span>
          ) : (
            <span className="inline-flex items-center gap-2 text-xs font-bold text-ink-soft">
              <span className="h-2.5 w-2.5 rounded-full bg-mint" /> all calm
            </span>
          )}
        </div>
      </aside>

      <main className="flex flex-1 flex-col overflow-hidden">
        <header className="relative flex items-center gap-3 border-b-[3px] border-ink/10 px-6 py-3">
          <span className="flex min-w-0 items-center gap-2 rounded-full border-[3px] border-ink/10 bg-cloud px-3 py-1.5 shadow-puff-sm">
            <Folder className="h-4 w-4 shrink-0 text-ink-soft" strokeWidth={2.2} />
            <span className="truncate text-sm font-bold text-ink/70">{repoRoot.data ?? "finding repo…"}</span>
          </span>
          {running && (
            <span className="text-xs font-bold text-ink-soft">
              {running}
              {progress && progress.total > 0 ? ` · ${progress.current}/${progress.total}` : "…"}
            </span>
          )}
          {running && (
            <div className="absolute inset-x-0 bottom-0 h-1 overflow-hidden bg-ink/5">
              {progress && progress.total > 0 ? (
                <div
                  className="h-full bg-blue transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.round((progress.current / progress.total) * 100))}%` }}
                />
              ) : (
                <div className="absolute h-full rounded-full bg-blue animate-indeterminate" />
              )}
            </div>
          )}
        </header>
        <div className="flex-1 overflow-auto p-6">
          {view === "dashboard" && (
            <Dashboard
              onNavigate={(category) => {
                setSkillsFocus(category);
                setView("skills");
              }}
            />
          )}
          {view === "skills" && (
            <Skills focusCategory={skillsFocus} onFocusHandled={() => setSkillsFocus(null)} />
          )}
          {view === "health" && <Health />}
          {view === "settings" && <SettingsView onRepoChange={() => repoRoot.reload()} />}
        </div>
      </main>

      {running === "bootstrap" && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-5 bg-cream/85 backdrop-blur-sm">
          <CoffeeLoader />
          <p className="text-lg font-black">Brewing the upstream CLI…</p>
          <p className="text-sm font-semibold text-ink-soft">installing deps &amp; building — this takes a minute</p>
        </div>
      )}
    </div>
  );
}
