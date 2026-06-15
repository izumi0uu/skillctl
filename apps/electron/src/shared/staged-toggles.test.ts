import { describe, expect, test } from "vitest";

import { applyToggle } from "./staged-toggles";

describe("applyToggle", () => {
  test("stages a change away from the saved state", () => {
    const next = applyToggle(new Map(), "x", true, true); // shown on, saved on -> turn off
    expect(next.get("x")).toBe(false);
  });

  test("clears the staged entry when toggled back to the saved state", () => {
    const pending = new Map([["x", false]]); // staged off, saved on
    const next = applyToggle(pending, "x", false, true); // shown off -> turn on (== saved)
    expect(next.has("x")).toBe(false);
  });

  test("does not mutate the input map", () => {
    const pending = new Map<string, boolean>();
    applyToggle(pending, "x", true, true);
    expect(pending.size).toBe(0);
  });
});
