---
name: watch-hot-node
description: Capture evidence for short-lived hot `node` or `codex` processes on macOS. Use when CPU spikes disappear before you can inspect them manually and you need a bundled watcher that snapshots `ps`, parent chain, cwd, open files, network sockets, and a short `sample` profile.
---

# Watch Hot Node

Use this skill for local macOS process forensics when a `node` or `codex` process briefly pegs CPU and exits before normal inspection is possible.

## What It Does

- Watches `node` and `codex` processes for CPU above a threshold.
- Captures evidence into `~/.hermes/logs/node-hot-watch/`.
- Can run once for an immediate scan or install a persistent `launchd` watcher.
- Produces event folders with:
  - `ps.txt`
  - `parent-chain.txt`
  - `cwd.txt`
  - `open-files.txt`
  - `network.txt`
  - `sample.txt`
  - `summary.txt`

## When To Use

- A build, test runner, bundler, or agent process spikes CPU and is gone before `ps` or Activity Monitor can explain it.
- The user asks what a hot `node` process actually was.
- The user wants to keep a background watcher installed and only log on real spikes.

## Boundaries

- macOS only. This skill depends on `launchctl` and `sample`.
- Do not claim a root cause from CPU alone. Read `parent-chain.txt`, `cwd.txt`, and `sample.txt` together.
- Prefer the bundled script over hand-editing the generated `LaunchAgent` plist.

## Workflow

### 1. Check Current State

Use the bundled script:

```bash
~/.codex/skills/watch-hot-node/scripts/watch_hot_node.sh --status
```

If you are not in Codex, use the same relative path inside that agent's installed `watch-hot-node` skill directory.

### 2. Install The Persistent Watcher

```bash
~/.codex/skills/watch-hot-node/scripts/watch_hot_node.sh --install-launch-agent
```

Useful environment overrides:

- `WATCH_CPU_THRESHOLD`
- `WATCH_INTERVAL_SEC`
- `WATCH_SAMPLE_DURATION_SEC`
- `WATCH_SAMPLE_INTERVAL_MS`
- `WATCH_COOLDOWN_SEC`
- `WATCH_VERBOSE`
- `WATCH_LOG_ROOT`

### 3. Reproduce The Spike

Let the workload run. The watcher stays quiet unless it captures a hot process.

Primary log:

```bash
tail -n 80 ~/.hermes/logs/node-hot-watch/watcher.log
```

### 4. Inspect The Latest Event

```bash
ls -1dt ~/.hermes/logs/node-hot-watch/event-* | head
sed -n '1,200p' ~/.hermes/logs/node-hot-watch/event-*/summary.txt
sed -n '1,120p' ~/.hermes/logs/node-hot-watch/event-*/parent-chain.txt
```

Read order:

1. `summary.txt` for timestamp, PID, cwd, and sample status
2. `parent-chain.txt` to see who launched it
3. `ps.txt` and `target-and-parent.txt` for command line and CPU snapshot
4. `sample.txt` for hot stack interpretation
5. `open-files.txt` and `network.txt` for I/O context

### 5. Run A One-Off Capture

If the hot process is still running now:

```bash
~/.codex/skills/watch-hot-node/scripts/watch_hot_node.sh --once
```

### 6. Stop The Watcher

```bash
~/.codex/skills/watch-hot-node/scripts/watch_hot_node.sh --stop
```

## Interpretation Hints

- A `cwd` under your app repo plus a parent like `npm run build` usually means the spike belongs to your workload, not the editor or agent host.
- Repeated `rollup`, `vite`, `tsc`, string encoding, or V8 scavenger frames usually point to compile or bundle work rather than network waits.
- Empty `network.txt` plus heavy `sample.txt` CPU stacks usually means compute-bound or GC-heavy work.

## Bundled Resources

- `scripts/watch_hot_node.sh` installs, runs, and stops the watcher.
