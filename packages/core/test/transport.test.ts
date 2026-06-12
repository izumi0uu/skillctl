import { describe, expect, test } from "vitest";

import { transportHealth } from "../src/transport.js";

describe("transportHealth", () => {
  test("accepts copy fallback without probing", async () => {
    const status = await transportHealth({
      sourceRoots: [],
      privateRoots: [],
      enabledAdapters: ["codex"],
      excludeSkills: [],
      liveProbePolicy: "off",
      transport: {
        mode: "copy-fallback",
        command: "npx",
        args: ["--yes", "skills"],
      },
      stateDir: "/tmp/skillctl-state",
    });
    expect(status.ok).toBe(true);
  });
});
