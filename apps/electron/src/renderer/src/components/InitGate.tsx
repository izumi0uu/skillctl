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
      <span className="grid h-20 w-20 place-items-center rounded-3xl border-[3px] border-lemon-ring bg-lemon shadow-puff animate-float">
        <Puzzle className="h-10 w-10" strokeWidth={2.2} />
      </span>
      <h1 className="text-2xl font-black">This folder isn’t a skillctl repo yet</h1>
      <p className="max-w-lg break-words font-semibold text-ink-soft">{repoRoot.data ?? "…"}</p>
      <div className="flex gap-3">
        <Button variant="blue" onClick={initialize} disabled={busy}>
          {busy ? "Initializing…" : "Initialize here"}
        </Button>
        <Button variant="ghost" onClick={choose}>
          Choose another folder
        </Button>
      </div>
    </div>
  );
}
