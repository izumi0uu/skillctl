import { beforeEach, describe, expect, test, vi } from "vitest";

const execFileAsyncMock = vi.fn();

vi.mock("node:child_process", () => ({
  execFile: (file: string, args: string[], options: unknown, callback?: (error: Error | null, result?: { stdout?: string; stderr?: string }) => void) => {
    const cb = typeof options === "function" ? options as typeof callback : callback;
    void execFileAsyncMock(file, args, options)
      .then((result: { stdout?: string; stderr?: string } | undefined) => cb?.(null, result))
      .catch((error: Error) => cb?.(error));
  },
}));

describe("verifyCatalogSources", () => {
  beforeEach(() => {
    execFileAsyncMock.mockReset();
  });

  test("rejects unsafe upstream refs before invoking git", async () => {
    const { verifyCatalogSources } = await import("../src/source-verification.js");
    const report = await verifyCatalogSources({
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "upstream",
        origin_kind: "imported-upstream",
        hash: "placeholder",
        managed: true,
        targets: ["codex"],
        canonical_rel_path: "skills/test/alpha",
        upstream: {
          repo: "owner/repo",
          ref: "--upload-pack=malicious",
          skillPath: "skills/alpha",
          sourceType: "github",
        },
      }],
    });

    expect(report.ok).toBe(false);
    expect(execFileAsyncMock).not.toHaveBeenCalled();
    expect(report.results).toEqual([{
      skill_id: "alpha",
      status: "error",
      detail: "upstream repo or ref begins with '-' and is rejected for git safety",
    }]);
  });

  test("treats unresolved exact commit pins as non-fatal skip", async () => {
    execFileAsyncMock.mockImplementation(async (_file: string, args: string[]) => {
      if (args[0] === "ls-remote" && args.length === 4) {
        return { stdout: "" };
      }
      if (args[0] === "init" || args[0] === "remote") {
        return { stdout: "" };
      }
      if (args[0] === "fetch") {
        throw new Error("not reachable");
      }
      if (args[0] === "ls-remote" && args.length === 3) {
        return { stdout: "" };
      }
      throw new Error(`unexpected git invocation: ${args.join(" ")}`);
    });

    const { verifyCatalogSources } = await import("../src/source-verification.js");
    const report = await verifyCatalogSources({
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "upstream",
        origin_kind: "imported-upstream",
        hash: "placeholder",
        managed: true,
        targets: ["codex"],
        canonical_rel_path: "skills/test/alpha",
        upstream: {
          repo: "owner/repo",
          ref: "0123456789abcdef0123456789abcdef01234567",
          skillPath: "skills/alpha",
          sourceType: "github",
        },
      }],
    });

    expect(report.ok).toBe(true);
    expect(report.results).toEqual([
      expect.objectContaining({
        skill_id: "alpha",
        status: "skip",
      }),
    ]);
  });

  test("retries transient ls-remote failures before succeeding", async () => {
    let calls = 0;
    execFileAsyncMock.mockImplementation(async (_file: string, args: string[]) => {
      if (args[0] === "ls-remote" && args.length === 4) {
        calls += 1;
        if (calls === 1) {
          throw new Error("fatal: unable to access remote: Operation timed out");
        }
        return { stdout: "0123456789abcdef0123456789abcdef01234567\trefs/heads/main\n" };
      }
      throw new Error(`unexpected git invocation: ${args.join(" ")}`);
    });

    const { verifyCatalogSources } = await import("../src/source-verification.js");
    const report = await verifyCatalogSources({
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "upstream",
        origin_kind: "imported-upstream",
        hash: "placeholder",
        managed: true,
        targets: ["codex"],
        canonical_rel_path: "skills/test/alpha",
        upstream: {
          repo: "owner/repo",
          ref: "main",
          skillPath: "skills/alpha",
          sourceType: "github",
        },
      }],
    });

    expect(calls).toBe(2);
    expect(report.ok).toBe(true);
    expect(report.results).toEqual([
      expect.objectContaining({
        skill_id: "alpha",
        status: "ok",
        resolved_ref: "0123456789abcdef0123456789abcdef01234567",
      }),
    ]);
  });

  test("treats exhausted connectivity failures as skip instead of hard error", async () => {
    execFileAsyncMock.mockImplementation(async (_file: string, args: string[]) => {
      if (args[0] === "ls-remote") {
        throw new Error("fatal: unable to access remote: Failed to connect to host");
      }
      throw new Error(`unexpected git invocation: ${args.join(" ")}`);
    });

    const { verifyCatalogSources } = await import("../src/source-verification.js");
    const report = await verifyCatalogSources({
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "upstream",
        origin_kind: "imported-upstream",
        hash: "placeholder",
        managed: true,
        targets: ["codex"],
        canonical_rel_path: "skills/test/alpha",
        upstream: {
          repo: "owner/repo",
          ref: "main",
          skillPath: "skills/alpha",
          sourceType: "github",
        },
      }],
    });

    expect(report.ok).toBe(true);
    expect(report.results).toEqual([
      {
        skill_id: "alpha",
        status: "skip",
        detail: "verification skipped for owner/repo: temporary remote connectivity failure",
      },
    ]);
  });

  test("treats timed out git child termination as skip instead of hard error", async () => {
    execFileAsyncMock.mockImplementation(async (_file: string, args: string[]) => {
      if (args[0] === "ls-remote") {
        const error = new Error("Command failed: git ls-remote -- https://github.com/owner/repo.git main");
        Object.assign(error, {
          killed: true,
          signal: "SIGTERM",
          code: null,
          stdout: "",
          stderr: "",
        });
        throw error;
      }
      throw new Error(`unexpected git invocation: ${args.join(" ")}`);
    });

    const { verifyCatalogSources } = await import("../src/source-verification.js");
    const report = await verifyCatalogSources({
      version: 1,
      generatedBy: "test",
      skills: [{
        skill_id: "alpha",
        visibility: "public",
        source_kind: "upstream",
        origin_kind: "imported-upstream",
        hash: "placeholder",
        managed: true,
        targets: ["codex"],
        canonical_rel_path: "skills/test/alpha",
        upstream: {
          repo: "owner/repo",
          ref: "main",
          skillPath: "skills/alpha",
          sourceType: "github",
        },
      }],
    });

    expect(report.ok).toBe(true);
    expect(report.results).toEqual([
      {
        skill_id: "alpha",
        status: "skip",
        detail: "verification skipped for owner/repo: temporary remote connectivity failure",
      },
    ]);
  });
});
