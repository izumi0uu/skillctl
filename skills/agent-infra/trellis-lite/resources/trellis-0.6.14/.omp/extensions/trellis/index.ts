import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import { existsSync, lstatSync, readFileSync, readdirSync, realpathSync, statSync } from "node:fs";
import { join, dirname, isAbsolute, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";

// ---------------------------------------------------------------------------
// Project root detection
// ---------------------------------------------------------------------------

function findProjectRoot(startDir: string): string | null {
   let current = startDir;
   while (true) {
      if (existsSync(join(current, ".trellis"))) return current;
      const parent = dirname(current);
      if (parent === current) break;
      current = parent;
   }
   return null;
}

// ---------------------------------------------------------------------------
// Session identity helpers (mirrors Python _sanitize_key / _hash_value / _context_key)
// ---------------------------------------------------------------------------

function sanitizeKey(raw: string): string {
   const safe = raw.trim().replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._-]+|[._-]+$/g, "");
   return safe ? safe.slice(0, 160) : "";
}

function hashValue(raw: string): string {
   return createHash("sha256").update(raw).digest("hex").slice(0, 24);
}

function buildContextKey(platformName: string, kind: string, value: string): string {
   if (kind === "transcript") {
      return `${platformName}_transcript_${hashValue(value)}`;
   }
   const safeValue = sanitizeKey(value);
   return safeValue ? `${platformName}_${safeValue}` : `${platformName}_${hashValue(value)}`;
}

function deriveContextKey(ctx?: { sessionManager?: { getSessionId?: () => string | undefined; getSessionFile?: () => string | undefined } }): string | null {
   const sessionId = ctx?.sessionManager?.getSessionId?.();
   if (sessionId) {
      return buildContextKey("omp", "session", sessionId);
   }
   const sessionFile = ctx?.sessionManager?.getSessionFile?.();
   if (sessionFile) {
      return buildContextKey("omp", "transcript", sessionFile);
   }
   const override = process.env.TRELLIS_CONTEXT_ID?.trim();
   return override ? sanitizeKey(override) || hashValue(override) : null;
}

function isInsideRoot(root: string, candidate: string): boolean {
   const rel = relative(root, candidate);
   return rel === "" || (rel !== ".." && !rel.startsWith("../") && !rel.startsWith("..\\") && !isAbsolute(rel));
}

// Keep the upstream 0.6.14 channel trust contract. Task/spec symlinks may
// resolve outside the checkout only when Trellis explicitly trusts that root.
const AUTO_TRUST_ENTRIES = ["tasks", "workspace"];

function stripTrustValue(value: string): string {
   return value.trim().replace(/\s*#.*$/, "").trim().replace(/^['"]|['"]$/g, "");
}

function parseChannelTrustSection(content: string): { trustedDirs: string[]; autoTrustSymlinks?: boolean } {
   const trustedDirs: string[] = [];
   let autoTrustSymlinks: boolean | undefined;
   let inChannel = false;
   let inList = false;

   for (const raw of content.split("\n")) {
      const line = raw.replace(/\r$/, "");
      const trimmed = line.trimEnd();
      if (trimmed.trim().startsWith("#")) continue;
      if (/^channel:\s*$/.test(trimmed)) {
         inChannel = true;
         inList = false;
         continue;
      }
      if (!inChannel) continue;
      if (trimmed.trim() !== "" && /^\S/.test(line)) {
         inChannel = false;
         inList = false;
         continue;
      }
      if (trimmed.trim() === "") continue;
      if (inList) {
         const item = trimmed.match(/^ {4}-\s*(.+)$/);
         if (item) {
            const value = stripTrustValue(item[1]!);
            if (value) trustedDirs.push(value);
            continue;
         }
         inList = false;
      }
      if (/^ {2}trusted_context_dirs:\s*$/.test(trimmed)) {
         inList = true;
         continue;
      }
      const boolMatch = trimmed.match(/^ {2}auto_trust_trellis_symlinks:\s*(.+)$/);
      if (boolMatch) {
         const value = stripTrustValue(boolMatch[1]!).toLowerCase();
         if (value === "false") autoTrustSymlinks = false;
         else if (value === "true") autoTrustSymlinks = true;
         else process.stderr.write(`[channel] channel.auto_trust_trellis_symlinks: invalid value '${value}', ignoring\n`);
      }
   }
   return { trustedDirs, autoTrustSymlinks };
}

function resolveTrustedRoots(projectRoot: string): string[] {
   const configPath = join(projectRoot, ".trellis", "config.yaml");
   let config: { trustedDirs: string[]; autoTrustSymlinks?: boolean } = { trustedDirs: [] };
   if (existsSync(configPath)) {
      try {
         config = parseChannelTrustSection(readFileSync(configPath, "utf-8"));
      } catch {
         // Invalid optional trust configuration grants no additional access.
      }
   }

   const roots: string[] = [];
   for (const entry of config.trustedDirs) {
      try {
         roots.push(realpathSync(resolve(projectRoot, entry)));
      } catch {
         // Missing trust entries are ignored.
      }
   }
   if (config.autoTrustSymlinks !== false) {
      for (const entryName of AUTO_TRUST_ENTRIES) {
         const entryPath = join(projectRoot, ".trellis", entryName);
         try {
            if (lstatSync(entryPath).isSymbolicLink()) roots.push(realpathSync(entryPath));
         } catch {
            // Missing or broken optional symlinks grant no access.
         }
      }
   }
   return [...new Set(roots)];
}

function resolveProjectFile(projectRoot: string, file: string, trustedRoots: string[] = []): string | null {
   try {
      const rootReal = realpathSync(projectRoot);
      const targetReal = realpathSync(resolve(projectRoot, file));
      if (isInsideRoot(rootReal, targetReal)) return targetReal;
      return trustedRoots.some((root) => isInsideRoot(root, targetReal)) ? targetReal : null;
   } catch {
      return null;
   }
}

// Mirror Trellis Python runtime task resolution: relative names live under
// `.trellis/tasks`, `.trellis/...` stays repo-relative, and absolute canonical
// refs remain absolute. Every resolved task must still stay under the project
// root or an explicitly trusted Trellis root.
function normalizeStoredTaskReference(taskRef: string): string {
   const trimmed = taskRef.trim();
   if (!trimmed) return "";
   if (isAbsolute(trimmed)) return trimmed;
   let normalized = trimmed.replaceAll("\\", "/");
   while (normalized.startsWith("./")) normalized = normalized.slice(2);
   if (normalized.startsWith("tasks/")) return `.trellis/${normalized}`;
   return normalized;
}

function resolveStoredTaskDir(projectRoot: string, taskRef: string, trustedRoots: string[]): string | null {
   const normalized = normalizeStoredTaskReference(taskRef);
   if (!normalized) return null;

   const lexicalTaskDir = isAbsolute(normalized)
      ? normalized
      : normalized.startsWith(".trellis/")
         ? resolve(projectRoot, normalized)
         : resolve(projectRoot, ".trellis", "tasks", normalized);

   try {
      const taskReal = realpathSync(lexicalTaskDir);
      if (!statSync(taskReal).isDirectory() || !isTrustedPath(projectRoot, taskReal, trustedRoots)) return null;
      const taskJson = safeTaskFile(projectRoot, lexicalTaskDir, "task.json", trustedRoots);
      if (!taskJson || !statSync(taskJson).isFile()) return null;
      return lexicalTaskDir;
   } catch {
      return null;
   }
}

// ---------------------------------------------------------------------------
// Active task resolution
// ---------------------------------------------------------------------------

function resolveActiveTaskStatus(
   projectRoot: string,
   contextKey: string | null,
): { status: string; taskDir: string | null; taskTitle: string | null } {
   const sessionsDir = join(projectRoot, ".trellis", ".runtime", "sessions");
   if (!existsSync(sessionsDir)) return { status: "no_task", taskDir: null, taskTitle: null };

   // --- 通过 context key 解析 session 文件 ---
   let sessionFilePath: string | null = null;

   if (contextKey) {
      const candidate = join(sessionsDir, `${contextKey}.json`);
      if (existsSync(candidate)) {
         sessionFilePath = candidate;
      } else {
         return { status: "no_task", taskDir: null, taskTitle: null };
      }
   } else {
      // No identity: use single-session fallback only when there is exactly one session file.
      let sessionFiles: string[];
      try {
         sessionFiles = readdirSync(sessionsDir).filter((f) => f.endsWith(".json"));
      } catch {
         return { status: "no_task", taskDir: null, taskTitle: null };
      }
      if (sessionFiles.length === 1) {
         sessionFilePath = join(sessionsDir, sessionFiles[0]);
      } else {
         return { status: "no_task", taskDir: null, taskTitle: null };
      }
   }

   // --- 读取 session 数据 ---
   let sessionData: Record<string, unknown>;
   try {
      sessionData = JSON.parse(readFileSync(sessionFilePath, "utf-8"));
   } catch {
      return { status: "no_task", taskDir: null, taskTitle: null };
   }

   const currentTask = sessionData.current_task;
   if (typeof currentTask !== "string" || !currentTask)
      return { status: "no_task", taskDir: null, taskTitle: null };

   const trustedRoots = resolveTrustedRoots(projectRoot);
   const taskDir = resolveStoredTaskDir(projectRoot, currentTask, trustedRoots);
   if (!taskDir) return { status: "no_task", taskDir: null, taskTitle: null };

   const taskJsonPath = safeTaskFile(projectRoot, taskDir, "task.json", trustedRoots);
   if (!taskJsonPath) return { status: "no_task", taskDir: null, taskTitle: null };

   let taskData: Record<string, unknown>;
   try {
      taskData = JSON.parse(readFileSync(taskJsonPath, "utf-8"));
   } catch {
      return { status: "no_task", taskDir: null, taskTitle: null };
   }

   return {
      status: typeof taskData.status === "string" ? taskData.status : "planning",
      taskDir,
      taskTitle: typeof taskData.title === "string" ? taskData.title : null,
   };
}

// ---------------------------------------------------------------------------
// Session context — spawns get_context.py default mode (same as Claude hook)
// ---------------------------------------------------------------------------

const SESSION_CONTEXT_TIMEOUT_MS = 5000;

function buildSessionContext(projectRoot: string, contextKey: string | null): string {
   const script = join(projectRoot, ".trellis", "scripts", "get_context.py");
   if (!existsSync(script)) return "";

   try {
      const result = spawnSync("python3", [script], {
         cwd: projectRoot,
         encoding: "utf-8",
         env: contextKey
            ? { ...process.env, TRELLIS_CONTEXT_ID: contextKey }
            : process.env,
         timeout: SESSION_CONTEXT_TIMEOUT_MS,
         windowsHide: true,
      });
      if (result.status !== 0 || !result.stdout?.trim()) {
         return "";
      }
      return `<session-context>\n${result.stdout.trim()}\n</session-context>`;
   } catch {
      return "";
   }
}

// ---------------------------------------------------------------------------
// Task context — recoverable bounded cache plus a complete file manifest
// ---------------------------------------------------------------------------

type AgentType = "trellis-implement" | "trellis-check" | "trellis-research" | null;
type ContextStatus = "inline" | "truncated" | "omitted";
type ContextKind = "task-artifact" | "jsonl-manifest" | "context-file";
type LiteChangeMode = "P0" | "P1" | "P2" | "P3";
type LiteVerificationLevel = "V0" | "V1" | "V2" | "V3";

interface LiteProfile {
   status: "selected" | "unselected" | "invalid";
   change_mode: LiteChangeMode | null;
   verification_level: LiteVerificationLevel | null;
   checker: "off" | "report";
   allowed_paths: string[];
   forbidden_paths: string[];
   selected_by: string | null;
   scope_locked: boolean;
   max_verification_passes: number;
}

const TRELLIS_AGENTS = new Set(["trellis-implement", "trellis-check", "trellis-research"]);
const CHECKER_ALLOWED_TOOLS = new Set(["read", "grep", "glob", "ast_grep", "yield"]);
const LITE_CHANGE_MODES = new Set<LiteChangeMode>(["P0", "P1", "P2", "P3"]);
const LITE_VERIFICATION_LEVELS = new Set<LiteVerificationLevel>(["V0", "V1", "V2", "V3"]);

interface ContextEntry {
   path: string;
   absolutePath: string | null;
   kind: ContextKind;
   bytes: number | null;
   status: ContextStatus;
   reason: string | null;
   requiredRead: boolean;
   eligible: boolean;
   perFileLimit: number | null;
   sources: string[];
}

interface InlineSection {
   path: string;
   content: string;
}

const MAX_TASK_ARTIFACT_BYTES = 48 * 1024;
const MAX_CONTEXT_FILE_BYTES = 64 * 1024;
const MAX_JSONL_MANIFEST_BYTES = 1024 * 1024;
const MAX_TASK_CONTEXT_BYTES = 256 * 1024;
const TASK_CONTEXT_PREFIX = "<task-context>\n";
const TASK_CONTEXT_SUFFIX = "\n</task-context>";
const TASK_ARTIFACTS = ["prd.md", "design.md", "implement.md", "info.md"] as const;
const JSONL_MANIFESTS = ["implement.jsonl", "check.jsonl"] as const;

function projectRelativePath(projectRoot: string, path: string): string {
   const lexicalRoot = resolve(projectRoot);
   const lexicalPath = resolve(path);
   if (isInsideRoot(lexicalRoot, lexicalPath)) {
      return relative(lexicalRoot, lexicalPath).replaceAll("\\", "/") || ".";
   }
   try {
      return relative(realpathSync(projectRoot), realpathSync(path)).replaceAll("\\", "/") || ".";
   } catch {
      return relative(lexicalRoot, lexicalPath).replaceAll("\\", "/") || ".";
   }
}

function regularFileSize(path: string | null): number | null {
   if (!path) return null;
   try {
      const fileStat = statSync(path);
      return fileStat.isFile() ? fileStat.size : null;
   } catch {
      return null;
   }
}

function isTrustedPath(projectRoot: string, candidate: string, trustedRoots: string[]): boolean {
   const rootReal = realpathSync(projectRoot);
   return isInsideRoot(rootReal, candidate)
      || trustedRoots.some((root) => isInsideRoot(root, candidate));
}

function safeTaskFile(
   projectRoot: string,
   taskDir: string,
   fileName: string,
   trustedRoots: string[],
): string | null {
   try {
      const taskReal = realpathSync(taskDir);
      if (!isTrustedPath(projectRoot, taskReal, trustedRoots)) return null;
      const candidate = resolveProjectFile(projectRoot, join(taskDir, fileName), trustedRoots);
      return candidate && isInsideRoot(taskReal, candidate) ? candidate : null;
   } catch {
      return null;
   }
}

function boundedStringArray(value: unknown, limit = 64): string[] {
   if (!Array.isArray(value)) return [];
   return value
      .filter((item): item is string => typeof item === "string")
      .map((item) => item.trim().replaceAll("\\", "/"))
      .filter(Boolean)
      .slice(0, limit);
}

function liteProfileFromTask(taskData: Record<string, unknown>): LiteProfile {
   const raw = taskData.lite;
   if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return {
         status: "unselected",
         change_mode: null,
         verification_level: null,
         checker: "off",
         allowed_paths: [],
         forbidden_paths: [],
         selected_by: null,
         scope_locked: false,
         max_verification_passes: 0,
      };
   }

   const profile = raw as Record<string, unknown>;
   const changeMode = typeof profile.change_mode === "string"
      && LITE_CHANGE_MODES.has(profile.change_mode as LiteChangeMode)
      ? profile.change_mode as LiteChangeMode
      : null;
   const verificationLevel = typeof profile.verification_level === "string"
      && LITE_VERIFICATION_LEVELS.has(profile.verification_level as LiteVerificationLevel)
      ? profile.verification_level as LiteVerificationLevel
      : null;
   const checker = profile.checker === "report" ? "report" : "off";
   const defaultPasses = verificationLevel === "V0" ? 0 : verificationLevel === "V1" ? 1 : verificationLevel === "V2" ? 3 : 8;
   const requestedPasses = typeof profile.max_verification_passes === "number"
      && Number.isInteger(profile.max_verification_passes)
      ? Math.max(0, Math.min(8, profile.max_verification_passes))
      : defaultPasses;
   const valid = changeMode !== null && verificationLevel !== null;

   return {
      status: valid ? "selected" : "invalid",
      change_mode: changeMode,
      verification_level: verificationLevel,
      checker,
      allowed_paths: boundedStringArray(profile.allowed_paths),
      forbidden_paths: boundedStringArray(profile.forbidden_paths),
      selected_by: typeof profile.selected_by === "string" ? profile.selected_by.slice(0, 80) : null,
      scope_locked: profile.scope_locked !== false,
      max_verification_passes: requestedPasses,
   };
}

function truncateUtf8(data: Buffer, maxBytes: number, marker: string): string {
   if (data.length <= maxBytes) return data.toString("utf-8");
   const markerBytes = Buffer.byteLength(marker, "utf-8");
   const contentLimit = Math.max(0, maxBytes - markerBytes);
   let content = data.subarray(0, contentLimit).toString("utf-8");
   while (Buffer.byteLength(content, "utf-8") > contentLimit) {
      content = content.slice(0, -1);
   }
   if (content.endsWith("\uFFFD")) content = content.slice(0, -1);
   return `${content}${marker}`;
}

function selectedJsonlNames(agentType?: AgentType): Set<string> {
   if (agentType === "trellis-check") return new Set(["check.jsonl"]);
   if (agentType === "trellis-research") return new Set();
   return new Set(["implement.jsonl"]);
}

function taskIdentity(projectRoot: string, taskDir: string, trustedRoots: string[]): Record<string, unknown> {
   const identity: Record<string, unknown> = {
      path: projectRelativePath(projectRoot, taskDir),
      source_of_truth: "disk",
      injected_content: "bounded cache",
      captured_at: new Date().toISOString(),
   };
   try {
      const taskJsonPath = safeTaskFile(projectRoot, taskDir, "task.json", trustedRoots);
      if (!taskJsonPath) return identity;
      const taskData = JSON.parse(readFileSync(taskJsonPath, "utf-8")) as Record<string, unknown>;
      if (typeof taskData.title === "string") identity.title = taskData.title;
      if (typeof taskData.status === "string") identity.status = taskData.status;
      identity.lite = liteProfileFromTask(taskData);
   } catch {
      // The task directory remains enough for explicit recovery.
   }
   return identity;
}

function manifestLine(entry: ContextEntry): string {
   const record: Record<string, unknown> = {
      path: entry.path,
      kind: entry.kind,
      bytes: entry.bytes,
      status: entry.status,
      required_read: entry.requiredRead,
   };
   if (entry.sources.length > 0) record.via = entry.sources;
   if (entry.reason) record.reason = entry.reason;
   return `- ${JSON.stringify(record)}`;
}

function renderTaskContext(
   identity: Record<string, unknown>,
   entries: ContextEntry[],
   inlineSections: InlineSection[],
): string {
   const parts = [
      `## Task Identity\n\n${JSON.stringify(identity)}`,
      "## Recovery Contract\n\nDisk task/design/spec files are authoritative. "
         + "Injected text is only a session-start cache; inline means complete at capture time, not permanently current. "
         + "Read every required_read path and re-read any file changed after captured_at before relying on it.",
      `## File Manifest\n\n${entries.map(manifestLine).join("\n")}`,
   ];
   if (inlineSections.length > 0) {
      parts.push(
         `## Inline File Cache\n\n${inlineSections
            .map((section) => `### ${section.path}\n\n${section.content}`)
            .join("\n\n---\n\n")}`,
      );
   }
   return `${TASK_CONTEXT_PREFIX}${parts.join("\n\n")}${TASK_CONTEXT_SUFFIX}`;
}

function renderManifestOverflow(
   identity: Record<string, unknown>,
   entries: ContextEntry[],
): string {
   const recoveryEntries = entries.filter((entry) => entry.kind !== "context-file");
   recoveryEntries.push({
      path: identity.path,
      absolutePath: null,
      kind: "context-file",
      bytes: null,
      status: "omitted",
      reason: `file manifest metadata exceeded ${MAX_TASK_CONTEXT_BYTES} bytes; read the JSONL manifests from disk`,
      requiredRead: true,
      eligible: false,
      perFileLimit: null,
      sources: JSONL_MANIFESTS.map((name) => `${identity.path}/${name}`),
   });
   const rendered = renderTaskContext(identity, recoveryEntries, []);
   if (Buffer.byteLength(rendered, "utf-8") <= MAX_TASK_CONTEXT_BYTES) return rendered;

   const safeIdentity = {
      path: truncateUtf8(
         Buffer.from(identity.path ?? ""),
         4096,
         "[truncated task path]",
      ),
      source_of_truth: "disk",
   };
   return `${TASK_CONTEXT_PREFIX}## Task Identity\n\n${JSON.stringify(safeIdentity)}`
      + "\n\n## Manifest Overflow\n\nThe manifest could not fit in the automatic context budget. "
      + "Read the task directory and its JSONL manifests from disk."
      + TASK_CONTEXT_SUFFIX;
}

function isAllowedContextFile(
   projectRoot: string,
   taskDir: string,
   targetPath: string,
   trustedRoots: string[],
): boolean {
   const allowedRoots = [
      join(projectRoot, ".trellis", "spec"),
      join(taskDir, "research"),
   ];

   for (const root of allowedRoots) {
      try {
         const rootReal = realpathSync(root);
         if (!isTrustedPath(projectRoot, rootReal, trustedRoots)) continue;
         if (isInsideRoot(rootReal, targetPath)) return true;
      } catch {
         // Optional spec/research roots may not exist.
      }
   }
   return false;
}

export function buildTaskContext(projectRoot: string, taskDir: string, agentType?: AgentType): string {
   const trustedRoots = resolveTrustedRoots(projectRoot);
   const identity = taskIdentity(projectRoot, taskDir, trustedRoots);
   const entries: ContextEntry[] = [];
   const candidates: ContextEntry[] = [];
   const selected = selectedJsonlNames(agentType);
   const entriesByAbsolutePath = new Map<string, ContextEntry>();

   for (const fileName of TASK_ARTIFACTS) {
      const candidatePath = join(taskDir, fileName);
      const absolutePath = safeTaskFile(projectRoot, taskDir, fileName, trustedRoots);
      const bytes = regularFileSize(absolutePath);
      const entry: ContextEntry = {
         path: projectRelativePath(projectRoot, candidatePath),
         absolutePath,
         kind: "task-artifact",
         bytes,
         status: "omitted",
         reason: bytes === null ? "missing or not a regular file" : "automatic context budget exhausted",
         requiredRead: bytes !== null,
         eligible: bytes !== null,
         perFileLimit: MAX_TASK_ARTIFACT_BYTES,
         sources: [],
      };
      entries.push(entry);
      if (entry.eligible) candidates.push(entry);
   }

   const orderedJsonlNames = [
      ...JSONL_MANIFESTS.filter((name) => selected.has(name)),
      ...JSONL_MANIFESTS.filter((name) => !selected.has(name)),
   ];
   for (const jsonlName of orderedJsonlNames) {
      const jsonlPath = join(taskDir, jsonlName);
      const safeJsonlPath = safeTaskFile(projectRoot, taskDir, jsonlName, trustedRoots);
      const jsonlBytes = regularFileSize(safeJsonlPath);
      const isSelected = selected.has(jsonlName);
      const jsonlEntry: ContextEntry = {
         path: projectRelativePath(projectRoot, jsonlPath),
         absolutePath: safeJsonlPath,
         kind: "jsonl-manifest",
         bytes: jsonlBytes,
         status: "omitted",
         reason: jsonlBytes === null
            ? "missing or not a regular file"
            : isSelected
               ? "navigation manifest; referenced files are listed separately"
               : "not selected for the current agent role; read from disk on demand",
         requiredRead: false,
         eligible: false,
         perFileLimit: null,
         sources: [],
      };
      entries.push(jsonlEntry);
      if (jsonlBytes === null) continue;
      if (jsonlBytes > MAX_JSONL_MANIFEST_BYTES) {
         jsonlEntry.reason = `navigation manifest exceeds the ${MAX_JSONL_MANIFEST_BYTES}-byte parse limit`;
         jsonlEntry.requiredRead = isSelected;
         continue;
      }

      let lines: string[];
      try {
         lines = readFileSync(safeJsonlPath as string, "utf-8").split(/\r?\n/);
      } catch {
         continue;
      }
      for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
         const trimmed = lines[lineIndex].trim();
         if (!trimmed) continue;
         try {
            const row = JSON.parse(trimmed) as Record<string, unknown>;
            const file = typeof row.file === "string" ? row.file.trim() : "";
            if (!file) continue;
            const targetPath = resolveProjectFile(projectRoot, file, trustedRoots);
            if (!targetPath) {
               entries.push({
                  path: file,
                  absolutePath: null,
                  kind: "context-file",
                  bytes: null,
                  status: "omitted",
                  reason: "missing, unreadable, or outside the project root",
                  requiredRead: false,
                  eligible: false,
                  perFileLimit: null,
                  sources: [`${jsonlName}:${lineIndex + 1}`],
               });
               continue;
            }

            const existing = entriesByAbsolutePath.get(targetPath);
            if (existing) {
               existing.sources.push(`${jsonlName}:${lineIndex + 1}`);
               if (isSelected && !existing.eligible && isAllowedContextFile(projectRoot, taskDir, targetPath, trustedRoots)) {
                  existing.eligible = true;
                  existing.requiredRead = true;
                  existing.reason = "automatic context budget exhausted";
                  existing.perFileLimit = MAX_CONTEXT_FILE_BYTES;
                  candidates.push(existing);
               }
               continue;
            }

            const allowed = isAllowedContextFile(projectRoot, taskDir, targetPath, trustedRoots);
            const targetBytes = regularFileSize(targetPath);
            const eligible = allowed && isSelected && targetBytes !== null;
            const entry: ContextEntry = {
               path: projectRelativePath(projectRoot, targetPath),
               absolutePath: targetPath,
               kind: "context-file",
               bytes: targetBytes,
               status: "omitted",
               reason: !allowed
                  ? "outside allowed .trellis/spec or task research roots"
                  : targetBytes === null
                     ? "not a regular file"
                  : !isSelected
                     ? "not selected for the current agent role"
                     : "automatic context budget exhausted",
               requiredRead: eligible,
               eligible,
               perFileLimit: eligible ? MAX_CONTEXT_FILE_BYTES : null,
               sources: [`${jsonlName}:${lineIndex + 1}`],
            };
            entriesByAbsolutePath.set(targetPath, entry);
            entries.push(entry);
            if (entry.eligible) candidates.push(entry);
         } catch {
            // Seed rows and malformed lines without file references are non-fatal.
         }
      }
   }

   let inlineSections: InlineSection[] = [];
   let rendered = renderTaskContext(identity, entries, inlineSections);
   if (Buffer.byteLength(rendered, "utf-8") > MAX_TASK_CONTEXT_BYTES) {
      return renderManifestOverflow(identity, entries);
   }

   for (const entry of candidates) {
      if (!entry.absolutePath || entry.bytes === null || entry.perFileLimit === null) continue;
      let data: Buffer;
      try {
         data = readFileSync(entry.absolutePath);
      } catch {
         entry.eligible = false;
         entry.requiredRead = false;
         entry.reason = "unreadable at injection time";
         continue;
      }
      if (data.length === 0) {
         entry.eligible = false;
         entry.requiredRead = false;
         entry.reason = "empty file";
         continue;
      }
      if (entry.path.endsWith("/design.md") && data.length > entry.perFileLimit) {
         entry.reason = `canonical design exceeds the ${entry.perFileLimit}-byte inline limit`;
         continue;
      }

      const isTruncated = data.length > entry.perFileLimit;
      const marker = `\n\n[truncated by Trellis Lite; read the full source at ${JSON.stringify(entry.path)}]`;
      const content = isTruncated
         ? truncateUtf8(data, entry.perFileLimit, marker)
         : data.toString("utf-8");
      const previous = {
         status: entry.status,
         reason: entry.reason,
         requiredRead: entry.requiredRead,
      };
      entry.status = isTruncated ? "truncated" : "inline";
      entry.reason = isTruncated ? "partial inline cache; full disk file remains authoritative" : null;
      entry.requiredRead = isTruncated;

      const nextSections = [...inlineSections, { path: entry.path, content }];
      const nextRendered = renderTaskContext(identity, entries, nextSections);
      if (Buffer.byteLength(nextRendered, "utf-8") <= MAX_TASK_CONTEXT_BYTES) {
         inlineSections = nextSections;
         rendered = nextRendered;
      } else {
         entry.status = previous.status;
         entry.reason = "automatic context budget exhausted";
         entry.requiredRead = previous.requiredRead;
      }
   }

   const finalRendered = renderTaskContext(identity, entries, inlineSections);
   return Buffer.byteLength(finalRendered, "utf-8") <= MAX_TASK_CONTEXT_BYTES
      ? finalRendered
      : renderManifestOverflow(identity, entries);
}

// ---------------------------------------------------------------------------
// Per-turn cache — prevents redundant workflow-state resolution within a
// single event cascade (input, before_agent_start, and context fire closely)
// ---------------------------------------------------------------------------

const SESSION_OVERVIEW_TEXT =
   "Trellis workflow system active. Use skills and agents as directed by the workflow state.";

class TurnContextCache {
   private key: string | null = null;
   private timestamp = 0;
   private workflowMsg = "";
   private static readonly TTL_MS = 1500;

   get(projectRoot: string, contextKey: string | null, statusOverride?: string): { workflowMsg: string } {
      const now = Date.now();
      const cacheKey = `${projectRoot}:${contextKey ?? ""}:${statusOverride ?? ""}`;
      if (
         this.key === cacheKey &&
         now - this.timestamp < TurnContextCache.TTL_MS
      ) {
         return { workflowMsg: this.workflowMsg };
      }

      const status = statusOverride ?? resolveActiveTaskStatus(projectRoot, contextKey).status;

      const workflowPath = join(projectRoot, ".trellis", "workflow.md");
      let workflowMd = "";
      try { workflowMd = readFileSync(workflowPath, "utf-8"); } catch { }

      let workflowBody = "";
      if (workflowMd) {
         const blocks = parseWorkflowStateBlocks(workflowMd);
         const activeBlock = blocks.find((b) => b.status === status);
         if (activeBlock) {
            workflowBody = `[workflow-state:${activeBlock.status}]\n${activeBlock.content}\n[/workflow-state:${activeBlock.status}]`;
         }
      }
      if (!workflowBody) {
         workflowBody = "Refer to workflow.md for current step.";
      }

      this.workflowMsg = `<workflow-state>\n${workflowBody}\n</workflow-state>\n\n<session-overview>\n${SESSION_OVERVIEW_TEXT}\n</session-overview>`;

      this.key = cacheKey;
      this.timestamp = now;
      return { workflowMsg: this.workflowMsg };
   }
}

// ---------------------------------------------------------------------------
// Workflow-state tag parsing
// ---------------------------------------------------------------------------

const WORKFLOW_STATE_RE =
   /\[workflow-state:([A-Za-z0-9_-]+)\]\s*\n([\s\S]*?)\n\s*\[\/workflow-state:\1\]/g;

interface WorkflowStateBlock {
   status: string;
   content: string;
}

function parseWorkflowStateBlocks(markdown: string): WorkflowStateBlock[] {
   const blocks: WorkflowStateBlock[] = [];
   for (const match of markdown.matchAll(WORKFLOW_STATE_RE)) {
      blocks.push({
         status: match[1],
         content: match[2].trim(),
      });
   }
   return blocks;
}

// ---------------------------------------------------------------------------
// Sub-agent recovery
// ---------------------------------------------------------------------------

interface SessionEntryLike {
   type?: unknown;
   agent?: unknown;
   task?: unknown;
   message?: {
      role?: unknown;
      content?: unknown;
   };
}

interface SessionContextLike {
   sessionManager?: {
      getSessionId?: () => string | undefined;
      getSessionFile?: () => string | undefined;
      getEntries?: () => unknown[];
   };
}

function sessionEntries(ctx?: SessionContextLike): unknown[] {
   try {
      const entries = ctx?.sessionManager?.getEntries?.();
      return Array.isArray(entries) ? entries : [];
   } catch {
      return [];
   }
}

export function recoverAgentType(entries: unknown[]): AgentType {
   for (const rawEntry of entries) {
      if (!rawEntry || typeof rawEntry !== "object") continue;
      const entry = rawEntry as SessionEntryLike;
      if (entry.type === "session_init" && typeof entry.agent === "string" && TRELLIS_AGENTS.has(entry.agent)) {
         return entry.agent as AgentType;
      }
   }
   return null;
}

function messageText(content: unknown): string {
   if (typeof content === "string") return content;
   if (!Array.isArray(content)) return "";
   return content
      .filter((part): part is { type?: unknown; text: string } => (
         Boolean(part)
         && typeof part === "object"
         && typeof (part as { text?: unknown }).text === "string"
      ))
      .map((part) => part.text)
      .join("\n");
}

function normalizeTaskReference(value: string): string | null {
   const reference = value.replace(/`+$/, "");
   const parts = reference.split("/");
   if (
      parts.length < 3
      || parts[0] !== ".trellis"
      || parts[1] !== "tasks"
      || parts.slice(2).some((part) => !part || part === "." || part === "..")
   ) {
      return null;
   }
   return reference;
}

export function recoverExplicitTaskPath(entries: unknown[]): string | null {
   const references = new Set<string>();
   const activeTaskPattern = /(?:^|\n)[\t ]*(?:[-*#]+[\t ]*)?Active task:[\t ]*`?(\.trellis\/tasks\/[A-Za-z0-9._/-]*[A-Za-z0-9_-])`?[\t ]*[.!?]?[\t ]*(?=\r?$)/gim;

   for (const rawEntry of entries) {
      if (!rawEntry || typeof rawEntry !== "object") continue;
      const entry = rawEntry as SessionEntryLike;
      const text = entry.type === "session_init" && typeof entry.task === "string"
         ? entry.task
         : entry.type === "message" && entry.message?.role === "user"
            ? messageText(entry.message.content)
            : "";
      for (const match of text.matchAll(activeTaskPattern)) {
         const reference = normalizeTaskReference(match[1]!);
         if (reference) references.add(reference);
      }
   }

   return references.size === 1 ? [...references][0]! : null;
}

export function resolveExplicitTaskDir(projectRoot: string, taskReference: string): string | null {
   const normalized = normalizeTaskReference(taskReference);
   if (!normalized) return null;

   const trustedRoots = resolveTrustedRoots(projectRoot);
   const lexicalTaskDir = resolve(projectRoot, normalized);
   const taskReal = resolveProjectFile(projectRoot, normalized, trustedRoots);
   if (!taskReal) return null;

   try {
      const tasksRootReal = realpathSync(join(projectRoot, ".trellis", "tasks"));
      if (!isInsideRoot(tasksRootReal, taskReal) || !statSync(taskReal).isDirectory()) return null;
      const taskJson = resolveProjectFile(projectRoot, join(normalized, "task.json"), trustedRoots);
      if (!taskJson || !isInsideRoot(taskReal, taskJson) || !statSync(taskJson).isFile()) return null;
      return lexicalTaskDir;
   } catch {
      return null;
   }
}

function taskStatus(projectRoot: string, taskDir: string): string {
   const trustedRoots = resolveTrustedRoots(projectRoot);
   try {
      const taskJson = safeTaskFile(projectRoot, taskDir, "task.json", trustedRoots);
      if (!taskJson) return "planning";
      const data = JSON.parse(readFileSync(taskJson, "utf-8")) as Record<string, unknown>;
      return typeof data.status === "string" ? data.status : "planning";
   } catch {
      return "planning";
   }
}

function activeLiteProfile(projectRoot: string, contextKey: string | null): LiteProfile | null {
   const active = resolveActiveTaskStatus(projectRoot, contextKey);
   if (!active.taskDir) return null;
   const trustedRoots = resolveTrustedRoots(projectRoot);
   try {
      const taskJson = safeTaskFile(projectRoot, active.taskDir, "task.json", trustedRoots);
      if (!taskJson) return null;
      const taskData = JSON.parse(readFileSync(taskJson, "utf-8")) as Record<string, unknown>;
      const profile = liteProfileFromTask(taskData);
      return profile.status === "selected" ? profile : null;
   } catch {
      return null;
   }
}

function activeLiteState(
   projectRoot: string,
   contextKey: string | null,
): { declared: boolean; profile: LiteProfile | null } {
   const active = resolveActiveTaskStatus(projectRoot, contextKey);
   if (!active.taskDir) return { declared: false, profile: null };
   const trustedRoots = resolveTrustedRoots(projectRoot);
   try {
      const taskJson = safeTaskFile(projectRoot, active.taskDir, "task.json", trustedRoots);
      if (!taskJson) return { declared: false, profile: null };
      const taskData = JSON.parse(readFileSync(taskJson, "utf-8")) as Record<string, unknown>;
      const declared = Object.prototype.hasOwnProperty.call(taskData, "lite");
      const profile = liteProfileFromTask(taskData);
      return { declared, profile: profile.status === "selected" ? profile : null };
   } catch {
      return { declared: false, profile: null };
   }
}

function globMatches(pattern: string, value: string): boolean {
   let expression = "^";
   const normalized = pattern.trim().replaceAll("\\", "/").replace(/^\.\//, "");
   for (let index = 0; index < normalized.length; index += 1) {
      const char = normalized[index]!;
      if (char === "*" && normalized[index + 1] === "*") {
         expression += ".*";
         index += 1;
      } else if (char === "*") {
         expression += "[^/]*";
      } else if (char === "?") {
         expression += "[^/]";
      } else {
         expression += char.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      }
   }
   try {
      return new RegExp(`${expression}$`).test(value);
   } catch {
      return false;
   }
}

const TOOL_PATH_KEYS = new Set(["path", "file", "filepath", "file_path", "filename", "target", "targets", "files"]);

function collectToolPaths(value: unknown, keyHint = "", output: string[] = [], depth = 0): string[] {
   if (depth > 5 || output.length >= 64) return output;
   if (typeof value === "string") {
      if (TOOL_PATH_KEYS.has(keyHint.toLowerCase())) output.push(value);
      return output;
   }
   if (Array.isArray(value)) {
      for (const item of value) collectToolPaths(item, keyHint, output, depth + 1);
      return output;
   }
   if (!value || typeof value !== "object") return output;
   for (const [key, child] of Object.entries(value)) {
      collectToolPaths(child, key, output, depth + 1);
   }
   return output;
}

function profilePathViolation(
   projectRoot: string,
   profile: LiteProfile,
   input: unknown,
): string | null {
   if (!profile.scope_locked) return null;
   if (profile.allowed_paths.length === 0 && profile.forbidden_paths.length === 0) return null;
   const root = resolve(projectRoot);
   const paths = collectToolPaths(input);
   for (const rawPath of paths) {
      const lexical = isAbsolute(rawPath) ? resolve(rawPath) : resolve(root, rawPath);
      if (!isInsideRoot(root, lexical)) return `path escapes project root: ${rawPath}`;
      const relativePath = relative(root, lexical).replaceAll("\\", "/");
      if (relativePath === ".trellis" || relativePath.startsWith(".trellis/")) continue;
      if (profile.forbidden_paths.some((pattern) => globMatches(pattern, relativePath))) {
         return `path is forbidden by Lite profile: ${relativePath}`;
      }
      if (
         profile.allowed_paths.length > 0
         && !profile.allowed_paths.some((pattern) => globMatches(pattern, relativePath))
      ) {
         return `path is outside Lite profile allowlist: ${relativePath}`;
      }
   }
   return null;
}

function toolCommand(input: unknown): string {
   if (!input || typeof input !== "object") return "";
   const record = input as Record<string, unknown>;
   for (const key of ["command", "cmd", "script"]) {
      if (typeof record[key] === "string") return record[key];
   }
   return "";
}

function verificationCategories(command: string): Set<string> {
   const categories = new Set<string>();
   if (/\b(?:test|tests|pytest|jest|vitest|mocha|playwright|cypress)\b/i.test(command)) categories.add("test");
   if (/\b(?:lint|eslint|ruff|flake8|pylint|stylelint)\b/i.test(command)) categories.add("lint");
   if (/\b(?:typecheck|type-check|tsc|pyright|basedpyright|mypy)\b/i.test(command)) categories.add("typecheck");
   if (/\b(?:build|compile|pack|bundle)\b/i.test(command)) categories.add("build");
   if (/\b(?:e2e|integration|smoke)\b/i.test(command)) categories.add("e2e");
   return categories;
}

function verificationBudgetViolation(
   profile: LiteProfile,
   contextKey: string | null,
   command: string,
   calls: Map<string, number>,
): string | null {
   if (!contextKey || !command) return null;
   const categories = verificationCategories(command);
   if (categories.size === 0) return null;
   const key = `${contextKey}:${profile.verification_level}`;
   const used = calls.get(key) ?? 0;
   if (used >= profile.max_verification_passes) {
      return `verification budget exhausted for ${profile.verification_level}; authorize a follow-up before running another check`;
   }
   calls.set(key, used + 1);
   return null;
}

function childRecoveryError(agentType: Exclude<AgentType, null>): string {
   return `<task-context-error>\n${agentType} was detected from this session's session_init entry, `
      + "but its own user assignment does not contain exactly one valid "
      + "`Active task: .trellis/tasks/...` line. Trellis Lite will not infer a task from "
      + "another session. Stop and report the missing or ambiguous task reference.\n</task-context-error>";
}

// ---------------------------------------------------------------------------
// Extension entry point
// ---------------------------------------------------------------------------

export default function(pi: ExtensionAPI): void {
   let projectRoot: string | null = null;
   const turnCache = new TurnContextCache();
   let agentType: AgentType = null;
   let childTaskDir: string | null = null;
   let childTaskContext = "";
   let childTaskInjected = false;

   // Tracks compaction boundaries — context handler skips scanning when no
   // compaction has occurred since last injection.
   let lastCompactionTs = 0;
   let lastInjectionTs = 0;
   const verificationCalls = new Map<string, number>();

   const rememberContextKey = (ctx?: SessionContextLike): string | null => deriveContextKey(ctx);

   pi.on("session_start", async (_event, ctx) => {
      projectRoot = findProjectRoot(ctx.cwd);
      const contextKey = rememberContextKey(ctx);
      agentType = recoverAgentType(sessionEntries(ctx));

      if (!projectRoot) return;

      // Recover the child assignment from its own session_init entry before
      // the first model call. Never borrow a parent session's task pointer.
      if (agentType) return;

      const sessionContext = buildSessionContext(projectRoot, contextKey);
      if (sessionContext) {
         await pi.sendMessage({
            customType: "trellis-session-context",
            content: sessionContext,
            display: false,
         });
      }

      const { taskDir } = resolveActiveTaskStatus(projectRoot, contextKey);
      if (taskDir) {
         const taskContext = buildTaskContext(projectRoot, taskDir);
         if (taskContext) {
            await pi.sendMessage({
               customType: "trellis-task-context",
               content: taskContext,
               display: false,
            });
         }
      }

      ctx.ui.notify("Trellis workflow system available", "info");
   });

   pi.on("session_before_compact", async () => {
      lastCompactionTs = Date.now();
      childTaskInjected = false;
   });

   pi.on("before_agent_start", async (_event, ctx) => {
      if (!projectRoot) {
         projectRoot = findProjectRoot(ctx.cwd);
      }
      if (!projectRoot) return;
      const contextKey = rememberContextKey(ctx);
      const entries = sessionEntries(ctx);
      agentType ??= recoverAgentType(entries);

      if (agentType) {
         const explicitTask = recoverExplicitTaskPath(entries);
         const nextTaskDir = explicitTask ? resolveExplicitTaskDir(projectRoot, explicitTask) : null;
         if (nextTaskDir !== childTaskDir) {
            childTaskDir = nextTaskDir;
            childTaskContext = "";
            childTaskInjected = false;
         }
         if (!childTaskDir) {
            lastInjectionTs = Date.now();
            return {
               message: {
                  customType: "trellis-task-context",
                  content: childRecoveryError(agentType),
                  display: false,
               },
            };
         }

         if (!childTaskContext) {
            childTaskContext = buildTaskContext(projectRoot, childTaskDir, agentType);
         }
         const cached = turnCache.get(projectRoot, contextKey, taskStatus(projectRoot, childTaskDir));
         lastInjectionTs = Date.now();
         if (!childTaskInjected) {
            childTaskInjected = true;
            return {
               message: {
                  customType: "trellis-task-context",
                  content: `${childTaskContext}\n\n${cached.workflowMsg}`,
                  display: false,
               },
            };
         }
         return {
            message: {
               customType: "trellis-workflow-state",
               content: cached.workflowMsg,
               display: false,
            },
         };
      }

      // Persistent injection: workflow state for this turn
      const cached = turnCache.get(projectRoot, contextKey);
      lastInjectionTs = Date.now();

      return {
         message: {
            customType: "trellis-workflow-state",
            content: cached.workflowMsg,
            display: false,
         },
      };
   });

   // context fires before EVERY LLM API call (including tool-use continuations
   // and post-compaction agent.continue() paths). Acts as a safety net when
   // before_agent_start's persisted messages were removed by compaction.
   pi.on("context", async (event, ctx) => {
      if (!projectRoot) return;
      const contextKey = rememberContextKey(ctx);

      // Fast path: no compaction since last injection — messages are still present
      if (lastInjectionTs > lastCompactionTs) return;

      const cached = turnCache.get(
         projectRoot,
         contextKey,
         agentType && childTaskDir ? taskStatus(projectRoot, childTaskDir) : undefined,
      );
      if (!cached.workflowMsg) return;

      const messages = event.messages as { role?: string; customType?: string }[];
      const hasTaskContext = messages.some(
         (message) => message.role === "custom" && message.customType === "trellis-task-context",
      );
      const hasWorkflowContext = messages.some(
         (message) => message.role === "custom" && message.customType === "trellis-workflow-state",
      );
      if (hasTaskContext && hasWorkflowContext) {
         lastInjectionTs = Date.now();
         childTaskInjected = agentType ? hasTaskContext : childTaskInjected;
         return;
      }

      lastInjectionTs = Date.now();
      const injectedMessages = [...event.messages];
      if (!hasTaskContext) {
         let taskContext: string | null = null;
         if (agentType) {
            taskContext = childTaskContext
               ?? (childTaskDir ? buildTaskContext(projectRoot, childTaskDir, agentType) : null);
         } else {
            const { taskDir } = resolveActiveTaskStatus(projectRoot, contextKey);
            taskContext = taskDir ? buildTaskContext(projectRoot, taskDir) : null;
         }
         if (taskContext) {
            if (agentType) childTaskContext = taskContext;
            injectedMessages.push({
               role: "custom",
               customType: "trellis-task-context",
               content: taskContext,
               timestamp: Date.now(),
            });
            if (agentType) childTaskInjected = true;
         } else if (agentType) {
            injectedMessages.push({
               role: "custom",
               customType: "trellis-task-context",
               content: childRecoveryError(agentType),
               timestamp: Date.now(),
            });
            childTaskInjected = false;
         }
      }
      if (!hasWorkflowContext) {
         injectedMessages.push({
            role: "custom",
            customType: "trellis-workflow-state",
            content: cached.workflowMsg,
            timestamp: Date.now(),
         });
      }
      return {
         messages: injectedMessages,
      };
   });

   // Keep task.py selection session-local without mutating process.env, which
   // is shared by every in-process OMP child agent.
   pi.on("tool_call", (event, ctx) => {
      agentType ??= recoverAgentType(sessionEntries(ctx));
      if (agentType === "trellis-check" && !CHECKER_ALLOWED_TOOLS.has(event.toolName)) {
         return {
            block: true,
            reason: `Trellis Lite checker blocked non-inspection tool: ${event.toolName}`,
         };
      }
      const contextKey = rememberContextKey(ctx);
      if (projectRoot && ["write", "edit", "apply_patch"].includes(event.toolName)) {
         const state = activeLiteState(projectRoot, contextKey);
         if (state.declared && !state.profile) {
            const paths = collectToolPaths(event.input);
            const productPath = paths.some((rawPath) => {
               const lexical = isAbsolute(rawPath) ? resolve(rawPath) : resolve(projectRoot!, rawPath);
               const relativePath = relative(resolve(projectRoot!), lexical).replaceAll("\\", "/");
               return relativePath !== ".trellis" && !relativePath.startsWith(".trellis/");
            });
            if (productPath) {
               return {
                  block: true,
                  reason: "Trellis Lite profile is missing or invalid; select change mode and verification level before editing product files",
               };
            }
         }
         const profile = state.profile;
         if (profile) {
            const violation = profilePathViolation(projectRoot, profile, event.input);
            if (violation) {
               return {
                  block: true,
                  reason: `Trellis Lite ${profile.change_mode} scope boundary: ${violation}`,
               };
            }
         }
      }
      if (projectRoot && event.toolName === "bash") {
         const profile = activeLiteProfile(projectRoot, contextKey);
         if (profile) {
            const violation = verificationBudgetViolation(
               profile,
               contextKey,
               toolCommand(event.input),
               verificationCalls,
            );
            if (violation) {
               return {
                  block: true,
                  reason: `Trellis Lite ${profile.verification_level} scope boundary: ${violation}`,
               };
            }
         }
      }
      if (event.toolName !== "bash") return;
      if (!contextKey) return;
      const input = event.input as { env?: Record<string, string> };
      input.env = {
         TRELLIS_CONTEXT_ID: contextKey,
         ...input.env,
      };
   });

   pi.on("input", async (_event, ctx) => {
      if (!projectRoot) {
         projectRoot = findProjectRoot(ctx.cwd);
      }
      // Resolve projectRoot on first input if session_start missed it
      if (!projectRoot) return { action: "continue" };
      const contextKey = rememberContextKey(ctx);
      // Pre-warm the cache so before_agent_start and context can use it
      turnCache.get(projectRoot, contextKey);
      return { action: "continue" };
   });
}
