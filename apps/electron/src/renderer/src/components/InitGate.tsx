import { useState } from "react";
import { Puzzle } from "iconoir-react";

import { Button, useUi } from "./ui";
import { api, useAsync } from "../lib/api";

export function InitGate({ onReady }: { onReady: () => void }) {
  const { notify } = useUi();
  const repoRoot = useAsync(() => api.repoRoot());
  const [busy, setBusy] = useState(false);

  async function initialize() {
    setBusy(true);
    const res = await api.init();
    setBusy(false);
    if (res.ok) {
      notify("success", "Initialized!");
      onReady();
    } else {
      notify("error", res.error);
    }
  }

  async function choose() {
    const res = await api.chooseRepo();
    if (!res.ok) {
      notify("error", res.error);
      return;
    }
    if (res.data) {
      onReady();
    }
  }

  return (
    <div className="flex h-screen w-screen flex-col items-center justify-center gap-5 bg-cream p-8 text-center text-ink">
      <span className="grid h-16 w-16 place-items-center rounded-[1.25rem] border-2 border-lemon-ring/75 bg-lemon shadow-puff animate-float">
        <Puzzle className="h-8 w-8" strokeWidth={2.1} />
      </span>
      <h1 className="text-2xl font-black">This workspace isn’t initialized yet</h1>
      <p className="max-w-2xl break-words font-semibold text-ink-soft">
        skillctl stores its config, catalog, and local state in a workspace folder you choose.
      </p>
      <p className="max-w-lg break-words text-sm font-bold text-ink-soft">{repoRoot.data ?? "…"}</p>
      <div className="flex gap-3">
        <Button variant="blue" onClick={initialize} disabled={busy}>
          {busy ? "Initializing…" : "Initialize workspace here"}
        </Button>
        <Button variant="ghost" onClick={choose}>
          Choose workspace folder
        </Button>
      </div>
    </div>
  );
}
