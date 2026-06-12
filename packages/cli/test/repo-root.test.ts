import fs from "node:fs/promises";
import path from "node:path";

import { describe, expect, test } from "vitest";

import { findWorkspaceRoot } from "../src/repo-root.js";

describe("findWorkspaceRoot", () => {
  test("walks upward to the workspace root", async () => {
    const root = await fs.mkdtemp(path.join(process.cwd(), ".tmp-root-"));
    await fs.writeFile(path.join(root, "pnpm-workspace.yaml"), "packages:\n  - packages/*\n", "utf8");
    await fs.writeFile(path.join(root, "package.json"), "{ \"name\": \"root\" }\n", "utf8");
    const nested = path.join(root, "packages", "cli", "src");
    await fs.mkdir(nested, { recursive: true });

    await expect(findWorkspaceRoot(nested)).resolves.toBe(root);

    await fs.rm(root, { recursive: true, force: true });
  });
});
