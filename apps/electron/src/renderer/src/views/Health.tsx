import { Check, CheckCircle, Tools, WarningCircle, WarningTriangle } from "iconoir-react";

import { Badge, Button, type IconType, Panel, Spinner, useUi } from "../components/ui";
import { api, useAsync } from "../lib/api";

type StatusTone = "mint" | "lemon" | "red";
function statusInfo(status: "ok" | "warn" | "error"): { tone: StatusTone; icon: IconType } {
  if (status === "ok") return { tone: "mint", icon: Check };
  if (status === "warn") return { tone: "lemon", icon: WarningTriangle };
  return { tone: "red", icon: WarningCircle };
}

export function Health() {
  const { confirm, notify } = useUi();
  const doctor = useAsync(() => api.doctor());

  async function runRepair() {
    const ok = await confirm({
      title: "Repair?",
      body: "Re-sync managed skills into agent directories and re-run doctor.",
      confirmLabel: "Patch it up!",
    });
    if (!ok) {
      return;
    }
    const res = await api.repair();
    if (res.ok) {
      notify("success", "All patched up!");
      doctor.reload();
    } else {
      notify("error", `Repair flopped: ${res.error}`);
    }
  }

  if (doctor.loading) {
    return <Spinner />;
  }
  if (doctor.error || !doctor.data) {
    return <Panel><span className="font-bold text-red">{doctor.error ?? "no report"}</span></Panel>;
  }

  const report = doctor.data;

  return (
    <div className="flex flex-col gap-5">
      <h1 className="text-3xl font-black">Health</h1>

      <Panel className="flex items-center gap-4">
        <span
          className={`grid h-16 w-16 shrink-0 place-items-center rounded-full border-[3px] ${
            report.healthy ? "border-mint-ring bg-mint/12 text-mint" : "border-lemon-ring bg-lemon/15 text-lemon"
          }`}
        >
          {report.healthy ? (
            <CheckCircle className="h-9 w-9" strokeWidth={2.2} />
          ) : (
            <WarningTriangle className="h-9 w-9" strokeWidth={2.2} />
          )}
        </span>
        <div className="flex flex-col gap-1">
          <div className="text-xl font-black">{report.healthy ? "Everything's peachy!" : "Could use a hug"}</div>
          <div className="text-sm font-bold text-ink-soft">exit code {report.exitCode}</div>
        </div>
        <div className="ml-auto">
          <Button variant="grape" icon={Tools} onClick={runRepair}>
            Repair
          </Button>
        </div>
      </Panel>

      <Panel>
        <h3 className="mb-3 text-lg font-black">Issues · {report.issues.length}</h3>
        {report.issues.length === 0 ? (
          <p className="font-bold text-ink-soft">Nothing to see here.</p>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {report.issues.map((issue, index) => {
              const info = statusInfo(issue.status);
              return (
                <li
                  key={`${issue.code}-${index}`}
                  className="flex items-start gap-2.5 rounded-2xl border-2 border-ink/8 p-2.5"
                >
                  <Badge tone={info.tone} icon={info.icon}>{issue.status}</Badge>
                  <div className="text-sm">
                    <span className="font-extrabold">{issue.code}</span>
                    <span className="font-semibold text-ink-soft"> — {issue.detail}</span>
                    {issue.repairable && <span className="ml-2 font-bold text-grape">repairable</span>}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <div className="grid grid-cols-2 gap-5">
        <Panel>
          <h3 className="mb-3 text-lg font-black">Portability · {report.portability.length}</h3>
          {report.portability.length === 0 ? (
            <p className="font-bold text-ink-soft">No findings.</p>
          ) : (
            <div className="flex flex-col gap-2">
              {report.portability.map((entry) => (
                <div key={entry.skillId} className="flex items-center gap-2 text-sm">
                  <Badge tone={entry.classification === "needs-review" ? "lemon" : "neutral"}>
                    {entry.classification}
                  </Badge>
                  <span className="truncate font-semibold text-ink/70">{entry.skillId}</span>
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel>
          <h3 className="mb-3 text-lg font-black">Probes</h3>
          <div className="flex flex-col gap-2">
            {report.probes.map((probe) => {
              const info = statusInfo(probe.status);
              return (
                <div key={probe.agent} className="flex items-center gap-2 text-sm">
                  <Badge tone={info.tone} icon={info.icon}>{probe.status}</Badge>
                  <span className="font-bold text-ink/75">{probe.agent}</span>
                  <span className="truncate text-xs font-semibold text-ink-soft">{probe.detail}</span>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>
    </div>
  );
}
