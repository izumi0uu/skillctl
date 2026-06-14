import fs from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import {
  ATTRIBUTION_END,
  ATTRIBUTION_START,
  README_SOURCES_END,
  README_SOURCES_START,
  applySkillAttribution,
  buildSourceRegistry,
  injectManagedSkillTaxonomySection,
  injectManagedSkillSourcesSection,
  summarizeSourceRegistry,
  normalizeCatalogArtifacts,
  readmeSourceRegistryDrift,
} from "../src/attribution.js";
import type { SkillctlCatalog } from "../src/types.js";
import { makeTempDir, writeReadme, writeSkill } from "./helpers.js";

describe("attribution", () => {
  test("applies a deterministic attribution footer once", () => {
    const skill = {
      skill_id: "alpha",
      visibility: "public",
      source_kind: "upstream",
      origin_kind: "imported-upstream",
      hash: "abc",
      managed: true,
      targets: ["codex"] as const,
      upstream: {
        repo: "owner/repo",
        ref: "main",
        skillPath: "skills/alpha",
        sourceType: "github" as const,
        local_modifications: true,
      },
    };

    const first = applySkillAttribution("---\nname: alpha\ndescription: test\n---\n\n# alpha\n", skill);
    const second = applySkillAttribution(first, skill);
    expect(first).toContain(ATTRIBUTION_START);
    expect(first).toContain(ATTRIBUTION_END);
    expect(second).toBe(first);
  });

  test("renders README sources section deterministically", () => {
    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [
        {
          skill_id: "beta",
          category: "knowledge-and-research",
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
      ],
    };

    const rendered = injectManagedSkillSourcesSection("# skillctl\n", catalog);
    expect(rendered).toContain(README_SOURCES_START);
    expect(rendered).toContain(README_SOURCES_END);
    expect(rendered).toContain("Source URL");

    const registry = buildSourceRegistry(catalog);
    expect(registry.map((entry) => entry.skill_id)).toEqual(["alpha", "beta"]);
    expect(registry[0]?.category_label).toBe("Agent Infra");
    expect(registry[1]?.category_label).toBe("Knowledge And Research");
  });

  test("summarizes source registry by category and provenance", () => {
    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [
        {
          skill_id: "alpha",
          category: "agent-infra",
          visibility: "public",
          source_kind: "upstream",
          origin_kind: "derived-from-upstream",
          hash: "a",
          managed: true,
          tags: ["ops", "config"],
          targets: ["codex"],
          canonical_rel_path: "skills/agent-infra/alpha",
          upstream: {
            repo: "owner/repo",
            ref: "main",
            skillPath: "skills/alpha",
            sourceType: "github",
            sourceUrl: "https://example.com",
            last_verified_ref: "main",
            local_modifications: true,
          },
        },
        {
          skill_id: "beta",
          visibility: "private",
          source_kind: "local-private",
          origin_kind: "local-authored",
          hash: "b",
          managed: false,
          targets: ["codex"],
        },
      ],
    };

    const summary = summarizeSourceRegistry(buildSourceRegistry(catalog));
    expect(summary.totalSkills).toBe(2);
    expect(summary.byOriginKind["derived-from-upstream"]).toBe(1);
    expect(summary.bySourceKind.upstream).toBe(1);
    expect(summary.byCategory[0]?.id).toBe("agent-infra");
    expect(summary.byCategory[0]?.localModifiedSkills).toBe(1);
  });

  test("renders README taxonomy section deterministically", () => {
    const catalog: SkillctlCatalog = {
      version: 1,
      generatedBy: "test",
      skills: [
        {
          skill_id: "beta",
          category: "knowledge-and-research",
          tags: ["research", "portable"],
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
          tags: ["config", "health"],
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
      ],
    };

    const rendered = injectManagedSkillTaxonomySection("# skillctl\n", catalog);
    expect(rendered).toContain("## Managed Skill Taxonomy");
    expect(rendered).toContain("Agent Infra");
    expect(rendered).toContain("Knowledge And Research");
    expect(rendered).toContain("`alpha`");
    expect(rendered).toContain("`beta`");
  });

  test("normalizes skill footer and README together", async () => {
    const repoRoot = await makeTempDir("skillctl-attr-");
    const skillDir = path.join(repoRoot, "skills");
    await fs.mkdir(skillDir, { recursive: true });
    const alphaDir = await writeSkill(skillDir, "alpha", "hello");
    await writeReadme(repoRoot, "# skillctl\n");

    const catalog: SkillctlCatalog = {
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
        canonical_rel_path: path.relative(repoRoot, alphaDir),
        upstream: {
          repo: "owner/repo",
          ref: "main",
          skillPath: "skills/alpha",
          sourceType: "github",
          local_modifications: false,
        },
      }],
    };

    const result = await normalizeCatalogArtifacts(repoRoot, catalog);
    expect(result.catalogChanged).toBe(true);
    expect(result.readmeChanged).toBe(true);
    expect(await readmeSourceRegistryDrift(repoRoot, catalog)).toBe(false);

    const skillContent = await fs.readFile(path.join(alphaDir, "SKILL.md"), "utf8");
    expect(skillContent).toContain("## Source Attribution");
    expect(skillContent).toContain("owner/repo");
  });
});
