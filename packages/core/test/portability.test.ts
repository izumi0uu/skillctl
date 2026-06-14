import fs from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { analyzeSkillPortability } from "../src/portability.js";
import type { CatalogSkill } from "../src/types.js";
import { makeTempDir, writeSkill } from "./helpers.js";

function baseSkill(skillId: string): CatalogSkill {
  return {
    skill_id: skillId,
    visibility: "public",
    source_kind: "local-public",
    origin_kind: "local-authored",
    hash: "placeholder",
    managed: true,
    targets: ["claude-code", "codex", "pi", "hermes", "opencode"],
    canonical_rel_path: `skills/test/${skillId}`,
  };
}

describe("skill portability analysis", () => {
  test("classifies plain SKILL.md as portable", async () => {
    const root = await makeTempDir("skillctl-portable-");
    const skillDir = await writeSkill(root, "alpha", "portable body");

    const report = await analyzeSkillPortability(skillDir, baseSkill("alpha"));
    expect(report.classification).toBe("portable");
    expect(report.signals.usesStandardSkillMdOnly).toBe(true);
  });

  test("classifies Claude dynamic injection as claude-only", async () => {
    const root = await makeTempDir("skillctl-claude-only-");
    const skillDir = await writeSkill(root, "alpha", "!`echo hello`");

    const report = await analyzeSkillPortability(skillDir, baseSkill("alpha"));
    expect(report.classification).toBe("claude-only");
    expect(report.signals.hasClaudeDynamicContext).toBe(true);
    expect(report.allowedTargets).toEqual(["claude-code"]);
    expect(report.blockedTargets).toEqual(["codex", "pi", "hermes", "opencode"]);
  });

  test("does not classify fenced code examples as Claude dynamic injection", async () => {
    const root = await makeTempDir("skillctl-claude-fenced-");
    const skillDir = await writeSkill(
      root,
      "alpha",
      [
        "```bash",
        "!`date`",
        "```",
      ].join("\n"),
    );

    const report = await analyzeSkillPortability(skillDir, baseSkill("alpha"));
    expect(report.classification).toBe("portable");
    expect(report.signals.hasClaudeDynamicContext).toBe(false);
  });

  test("classifies openai manifest as codex-enhanced", async () => {
    const root = await makeTempDir("skillctl-codex-enhanced-");
    const skillDir = await writeSkill(root, "alpha", "portable body");
    await fs.mkdir(path.join(skillDir, "agents"), { recursive: true });
    await fs.writeFile(path.join(skillDir, "agents", "openai.yaml"), "skill:\n  display_name: Alpha\n", "utf8");

    const report = await analyzeSkillPortability(skillDir, baseSkill("alpha"));
    expect(report.classification).toBe("codex-enhanced");
    expect(report.signals.hasOpenAiManifest).toBe(true);
    expect(report.allowedTargets).toEqual(["claude-code", "codex", "pi", "hermes", "opencode"]);
  });

  test("classifies missing description as needs-review", async () => {
    const root = await makeTempDir("skillctl-needs-review-");
    const skillDir = path.join(root, "alpha");
    await fs.mkdir(skillDir, { recursive: true });
    await fs.writeFile(path.join(skillDir, "SKILL.md"), "---\nname: alpha\n---\n\n# alpha\n", "utf8");

    const report = await analyzeSkillPortability(skillDir, baseSkill("alpha"));
    expect(report.classification).toBe("needs-review");
    expect(report.signals.missingDescription).toBe(true);
  });

  test("classifies target mismatch as needs-review", async () => {
    const root = await makeTempDir("skillctl-target-mismatch-");
    const skillDir = await writeSkill(root, "alpha", "!`echo hello`");
    const skill = baseSkill("alpha");
    skill.targets = ["codex"];

    const report = await analyzeSkillPortability(skillDir, skill);
    expect(report.classification).toBe("claude-only");
    expect(report.signals.targetMismatch).toBe(true);
  });

  test("allows explicit portability overrides for non-structural policy blocks", async () => {
    const root = await makeTempDir("skillctl-portability-override-");
    const skillDir = await writeSkill(root, "alpha", "!`echo hello`");
    const skill = baseSkill("alpha");
    skill.distribution = {
      portability_allow_targets: ["codex"],
    };

    const report = await analyzeSkillPortability(skillDir, skill);
    expect(report.classification).toBe("claude-only");
    expect(report.allowedTargets).toEqual(["claude-code", "codex"]);
    expect(report.overrideTargets).toEqual(["codex"]);
  });
});
