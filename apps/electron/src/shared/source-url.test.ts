import { describe, expect, test } from "vitest";

import { sourceUrl } from "./source-url";

describe("sourceUrl", () => {
  test("prefers an explicit https source url", () => {
    expect(
      sourceUrl({ upstream_source_url: "https://github.com/o/r/tree/main/x", upstream_repo: "o/r" }),
    ).toBe("https://github.com/o/r/tree/main/x");
  });

  test("builds a github url from an owner/repo slug", () => {
    expect(sourceUrl({ upstream_source_url: null, upstream_repo: "o/r" })).toBe("https://github.com/o/r");
  });

  test("uses repo directly when it is itself an http url", () => {
    expect(sourceUrl({ upstream_source_url: null, upstream_repo: "https://gist.github.com/x.git" })).toBe(
      "https://gist.github.com/x.git",
    );
  });

  test("ignores file:// and local:// sources", () => {
    expect(
      sourceUrl({ upstream_source_url: "file:///Users/x/skill", upstream_repo: "local://hermes" }),
    ).toBeNull();
  });

  test("returns null when there is no provenance", () => {
    expect(sourceUrl(null)).toBeNull();
    expect(sourceUrl({ upstream_source_url: null, upstream_repo: null })).toBeNull();
  });
});
