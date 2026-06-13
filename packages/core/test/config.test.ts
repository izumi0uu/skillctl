import { describe, expect, test } from "vitest";

import { defaultConfig } from "../src/config.js";

describe("defaultConfig", () => {
  test("uses skills-cli transport by default", () => {
    const config = defaultConfig();
    expect(config.transport.mode).toBe("skills-cli");
    expect(config.transport.command).toBe("npx");
    expect(config.transport.args).toEqual(["--yes", "skills"]);
    expect(config.transport.embeddedRepoPath).toBe("vercel-skills");
  });
});
