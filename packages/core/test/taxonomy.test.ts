import { describe, expect, test } from "vitest";

import { buildManagedSkillTaxonomy } from "../src/taxonomy.js";
import type { SkillctlCatalog } from "../src/types.js";

describe("taxonomy", () => {
  test("groups skills deterministically and preserves tags", () => {
    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [
        {
          skill_id: "beta",
          category: "knowledge-and-research",
          tags: ["portable", "research"],
          visibility: "public",
          source_kind: "local-public",
          origin_kind: "local-authored",
          hash: "b",
          managed: true,
          targets: ["codex"],
        },
        {
          skill_id: "alpha",
          category: "agent-infra",
          tags: ["config"],
          visibility: "public",
          source_kind: "upstream",
          origin_kind: "imported-upstream",
          hash: "a",
          managed: true,
          targets: ["codex"],
          upstream: {
            repo: "owner/repo",
            ref: "main",
            skillPath: "skills/alpha",
            sourceType: "github",
            local_modifications: false,
          },
        },
        {
          skill_id: "gamma",
          visibility: "private",
          source_kind: "local-private",
          origin_kind: "local-authored",
          hash: "c",
          managed: false,
          targets: ["codex"],
        },
      ],
    };

    const taxonomy = buildManagedSkillTaxonomy(catalog);
    expect(taxonomy.categories.map((category) => category.id)).toEqual(["agent-infra", "knowledge-and-research", "uncategorized"]);
    expect(taxonomy.categories[0]?.skills.map((skill) => skill.skill_id)).toEqual(["alpha"]);
    expect(taxonomy.categories[2]?.skills[0]?.skill_id).toBe("gamma");
    expect(taxonomy.summary.totalSkills).toBe(3);
    expect(taxonomy.summary.uncategorizedSkills).toBe(1);
  });
});
