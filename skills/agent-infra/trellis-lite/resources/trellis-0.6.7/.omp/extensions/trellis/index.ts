import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent";
import { existsSync, readFileSync, readdirSync, realpathSync, statSync } from "node:fs";
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

function deriveContextKey(ctx?: { sessionManager?: { getSessionId?: () => string; getSessionFile?: () => string } }): string | null {
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

function resolveProjectFile(projectRoot: string, file: string): string | null {
   try {
      const rootReal = realpathSync(projectRoot);
      const targetReal = realpathSync(resolve(projectRoot, file));
      return isInsideRoot(rootReal, targetReal) ? targetReal : null;
   } catch {
      return null;
   }
}

// Mirror Trellis Python runtime task resolution while keeping 0.6.7 tasks
// inside the project root. Relative names live under `.trellis/tasks`, while
// `.trellis/...` references stay repo-relative.
function normalizeStoredTaskReference(taskRef: string): string {
   const trimmed = taskRef.trim();
   if (!trimmed) return "";
   if (isAbsolute(trimmed)) return trimmed;
   let normalized = trimmed.replaceAll("\\", "/");
   while (normalized.startsWith("./")) normalized = normalized.slice(2);
   if (normalized.startsWith("tasks/")) return `.trellis/${normalized}`;
   return normalized;
}

function resolveStoredTaskDir(projectRoot: string, taskRef: string): string | null {
   const normalized = normalizeStoredTaskReference(taskRef);
   if (!normalized) return null;

   const lexicalTaskDir = isAbsolute(normalized)
      ? normalized
      : normalized.startsWith(".trellis/")
         ? resolve(projectRoot, normalized)
         : resolve(projectRoot, ".trellis", "tasks", normalized);

   try {
      const rootReal = realpathSync(projectRoot);
      const taskReal = realpathSync(lexicalTaskDir);
      if (!statSync(taskReal).isDirectory() || !isInsideRoot(rootReal, taskReal)) return null;
      const taskJson = safeTaskFile(projectRoot, lexicalTaskDir, "task.json");
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

   const taskDir = resolveStoredTaskDir(projectRoot, currentTask);
   if (!taskDir) return { status: "no_task", taskDir: null, taskTitle: null };

   const taskJsonPath = safeTaskFile(projectRoot, taskDir, "task.json");
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

function safeTaskFile(projectRoot: string, taskDir: string, fileName: string): string | null {
   try {
      const taskReal = realpathSync(taskDir);
      const rootReal = realpathSync(projectRoot);
      if (!isInsideRoot(rootReal, taskReal)) return null;
      const candidate = resolveProjectFile(projectRoot, join(taskDir, fileName));
      return candidate && isInsideRoot(taskReal, candidate) ? candidate : null;
   } catch {
      return null;
   }
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

function taskIdentity(projectRoot: string, taskDir: string): Record<string, string> {
   const identity: Record<string, string> = {
      path: projectRelativePath(projectRoot, taskDir),
      source_of_truth: "disk",
      injected_content: "bounded cache",
      captured_at: new Date().toISOString(),
   };
   try {
      const taskJsonPath = safeTaskFile(projectRoot, taskDir, "task.json");
      if (!taskJsonPath) return identity;
      const taskData = JSON.parse(readFileSync(taskJsonPath, "utf-8")) as Record<string, unknown>;
      if (typeof taskData.title === "string") identity.title = taskData.title;
      if (typeof taskData.status === "string") identity.status = taskData.status;
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
   identity: Record<string, string>,
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
   identity: Record<string, string>,
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

function isAllowedContextFile(projectRoot: string, taskDir: string, targetPath: string): boolean {
   const allowedRoots = [
      join(projectRoot, ".trellis", "spec"),
      join(taskDir, "research"),
   ];

   for (const root of allowedRoots) {
      try {
         if (isInsideRoot(realpathSync(root), targetPath)) return true;
      } catch {
         // Optional spec/research roots may not exist.
      }
   }
   return false;
}

export function buildTaskContext(projectRoot: string, taskDir: string, agentType?: AgentType): string {
   const identity = taskIdentity(projectRoot, taskDir);
   const entries: ContextEntry[] = [];
   const candidates: ContextEntry[] = [];
   const selected = selectedJsonlNames(agentType);
   const entriesByAbsolutePath = new Map<string, ContextEntry>();

   for (const fileName of TASK_ARTIFACTS) {
      const candidatePath = join(taskDir, fileName);
      const absolutePath = safeTaskFile(projectRoot, taskDir, fileName);
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
      const safeJsonlPath = safeTaskFile(projectRoot, taskDir, jsonlName);
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
            const targetPath = resolveProjectFile(projectRoot, file);
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
               if (isSelected && !existing.eligible && isAllowedContextFile(projectRoot, taskDir, targetPath)) {
                  existing.eligible = true;
                  existing.requiredRead = true;
                  existing.reason = "automatic context budget exhausted";
                  existing.perFileLimit = MAX_CONTEXT_FILE_BYTES;
                  candidates.push(existing);
               }
               continue;
            }

            const allowed = isAllowedContextFile(projectRoot, taskDir, targetPath);
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

   get(projectRoot: string, contextKey: string | null): { workflowMsg: string } {
      const now = Date.now();
      const cacheKey = `${projectRoot}:${contextKey ?? ""}`;
      if (
         this.key === cacheKey &&
         now - this.timestamp < TurnContextCache.TTL_MS
      ) {
         return { workflowMsg: this.workflowMsg };
      }

      const { status } = resolveActiveTaskStatus(projectRoot, contextKey);

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
// Sub-agent detection
// ---------------------------------------------------------------------------

const TRELLIS_AGENTS = new Set(["trellis-implement", "trellis-check", "trellis-research"]);
const CHECKER_ALLOWED_TOOLS = new Set(["read", "grep", "glob", "ast_grep", "yield"]);

function detectAgentType(): AgentType {
   const blocked = process.env.PI_BLOCKED_AGENT;
   if (blocked && TRELLIS_AGENTS.has(blocked)) {
      return blocked as AgentType;
   }
   return null;
}

// ---------------------------------------------------------------------------
// Extension entry point
// ---------------------------------------------------------------------------

export default function(pi: ExtensionAPI): void {
   let projectRoot: string | null = null;
   const turnCache = new TurnContextCache();
   const agentType = detectAgentType();
   const isSubAgent = agentType !== null;

   // Tracks compaction boundaries — context handler skips scanning when no
   // compaction has occurred since last injection.
   let lastCompactionTs = 0;
   let lastInjectionTs = 0;

   const rememberContextKey = (ctx?: { sessionManager?: { getSessionId?: () => string; getSessionFile?: () => string } }): string | null => {
      const key = deriveContextKey(ctx);
      if (!key) return null;
      // AI-run shell commands inherit this value, keeping task.py pointers on
      // the same omp_* session key used by the extension's context injection.
      process.env.TRELLIS_CONTEXT_ID = key;
      return key;
   };

   pi.on("session_start", async (_event, ctx) => {
      projectRoot = findProjectRoot(ctx.cwd);
      const contextKey = rememberContextKey(ctx);

      if (!projectRoot) return;

      if (isSubAgent) {
         // Sub-agent: inject precise task context once
         const { taskDir } = resolveActiveTaskStatus(projectRoot, contextKey);
         if (taskDir) {
            const taskContext = buildTaskContext(projectRoot, taskDir, agentType);
            if (taskContext) {
               await pi.sendMessage({
                  customType: "trellis-task-context",
                  content: taskContext,
                  display: false,
               });
            }
         }
      } else {
         // Main session: inject session context (global map) + task context
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
      }
   });

   pi.on("session_before_compact", async () => {
      lastCompactionTs = Date.now();
   });

   pi.on("before_agent_start", async (_event, ctx) => {
      if (!projectRoot) {
         projectRoot = findProjectRoot(ctx.cwd);
      }
      if (!projectRoot) return;
      const contextKey = rememberContextKey(ctx);

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

      const cached = turnCache.get(projectRoot, contextKey);
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
         return;
      }

      lastInjectionTs = Date.now();
      const injectedMessages = [...event.messages];
      if (!hasTaskContext) {
         const { taskDir } = resolveActiveTaskStatus(projectRoot, contextKey);
         const taskContext = taskDir ? buildTaskContext(projectRoot, taskDir, agentType) : null;
         if (taskContext) {
            injectedMessages.push({
               role: "custom",
               customType: "trellis-task-context",
               content: taskContext,
               timestamp: Date.now(),
            });
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

   pi.on("tool_call", (event) => {
      if (agentType !== "trellis-check" || CHECKER_ALLOWED_TOOLS.has(event.toolName)) return;
      return {
         block: true,
         reason: `Trellis Lite checker blocked non-inspection tool: ${event.toolName}`,
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
