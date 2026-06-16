import { beforeEach, describe, expect, test, vi } from "vitest";

const readFileMock = vi.hoisted(() => vi.fn());
const writeFileMock = vi.hoisted(() => vi.fn());
const mkdirMock = vi.hoisted(() => vi.fn());
const accessMock = vi.hoisted(() => vi.fn());
const showOpenDialogMock = vi.hoisted(() => vi.fn());
const loadCatalogMock = vi.hoisted(() => vi.fn());
const getPathMock = vi.hoisted(() => vi.fn());
const electronApp = vi.hoisted(() => ({
  isPackaged: false,
  getPath: getPathMock,
}));

vi.mock("electron", () => ({
  app: electronApp,
  dialog: {
    showOpenDialog: showOpenDialogMock,
  },
}));

vi.mock("node:fs/promises", () => ({
  access: accessMock,
  mkdir: mkdirMock,
  readFile: readFileMock,
  writeFile: writeFileMock,
}));

vi.mock("@skillctl/core", () => ({
  loadCatalog: loadCatalogMock,
}));

const { __repoRootInternals, chooseRepoRoot, resolveInitialRepoRoot } = await import("./repo-root");

describe("repo-root", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    __repoRootInternals.resetForTests();
    electronApp.isPackaged = false;
    getPathMock.mockImplementation((name: string) => (name === "userData" ? "/tmp/user-data" : "/tmp/documents"));
    accessMock.mockImplementation(async (target: string) => {
      const ok = new Set([
        "/tmp/project/pnpm-workspace.yaml",
        "/tmp/project/package.json",
        "/tmp/existing/skillctl.catalog.json",
      ]);
      if (!ok.has(target)) {
        throw new Error(`ENOENT: ${target}`);
      }
    });
    readFileMock.mockResolvedValue('{"repoRoot":"/tmp/saved"}');
    writeFileMock.mockResolvedValue(undefined);
    mkdirMock.mockResolvedValue(undefined);
    showOpenDialogMock.mockResolvedValue({ canceled: false, filePaths: ["/tmp/workspace"] });
    loadCatalogMock.mockResolvedValue({});
  });

  test("findMonorepoRoot walks up to the workspace root", async () => {
    await expect(__repoRootInternals.findMonorepoRoot("/tmp/project/apps/electron/out")).resolves.toBe("/tmp/project");
  });

  test("defaults packaged builds to a standalone workspace path", () => {
    expect(__repoRootInternals.defaultPackagedWorkspace()).toBe("/tmp/documents/skillctl-workspace");
  });

  test("choosing a new workspace accepts folders without an existing catalog", async () => {
    await expect(chooseRepoRoot()).resolves.toBe("/tmp/workspace");
    expect(loadCatalogMock).not.toHaveBeenCalled();
    expect(writeFileMock).toHaveBeenCalled();
  });

  test("choosing an existing repo keeps the nearest skillctl root", async () => {
    showOpenDialogMock.mockResolvedValue({ canceled: false, filePaths: ["/tmp/existing/nested"] });

    await expect(chooseRepoRoot()).resolves.toBe("/tmp/existing");
    expect(loadCatalogMock).toHaveBeenCalledWith("/tmp/existing");
  });

  test("resolveInitialRepoRoot returns the persisted workspace in packaged mode", async () => {
    electronApp.isPackaged = true;

    await expect(resolveInitialRepoRoot()).resolves.toBe("/tmp/saved");
  });

  test("resolveInitialRepoRoot uses a default packaged workspace when nothing is saved", async () => {
    electronApp.isPackaged = true;
    readFileMock.mockRejectedValueOnce(new Error("missing"));

    await expect(resolveInitialRepoRoot()).resolves.toBe("/tmp/documents/skillctl-workspace");
    expect(writeFileMock).toHaveBeenCalled();
  });
});
