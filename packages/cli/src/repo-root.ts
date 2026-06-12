import fs from "node:fs/promises";
import path from "node:path";

export async function findWorkspaceRoot(startDir: string): Promise<string> {
  let current = startDir;
  while (true) {
    const workspaceFile = path.join(current, "pnpm-workspace.yaml");
    const packageFile = path.join(current, "package.json");
    const hasWorkspace = await fs.access(workspaceFile).then(() => true).catch(() => false);
    const hasPackage = await fs.access(packageFile).then(() => true).catch(() => false);
    if (hasWorkspace && hasPackage) {
      return current;
    }

    const parent = path.dirname(current);
    if (parent === current) {
      return startDir;
    }
    current = parent;
  }
}
