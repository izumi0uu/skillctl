---
name: watch-hot-node
description: Run a low-overhead Rust watcher that captures short-lived hot `node` or `codex` processes and correlates sustained WindowServer CPU spikes on macOS. Use when spikes disappear before inspection or the Mac runs hot and you need process, thermal, display, and graphical context.
---

# Watch Hot Node

Use this skill for local macOS process forensics when a `node` or `codex` process briefly pegs CPU and exits, or when WindowServer stays hot without identifying which visible workload is driving it.

## What It Does

- Watches `node` and `codex` processes for CPU above a threshold.
- Watches WindowServer with a separate threshold and cooldown.
- Uses interval CPU measurements for Node/Codex from a persistent Rust daemon.
- Uses one permitted `ps` reading per interval for root-owned WindowServer, whose cumulative CPU counters are restricted by macOS.
- Runs evidence capture asynchronously so a 5-second profile does not block the next CPU scan.
- Rotates old events by count and total disk usage.
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
  - `system-processes.txt`
  - `system-summary.txt`
  - `thermal.txt`
  - `event.json`
- WindowServer events also include:
  - `frontmost-app.txt`
  - `applications.txt`
  - `displays.txt`

## When To Use

- A build, test runner, bundler, or agent process spikes CPU and is gone before `ps` or Activity Monitor can explain it.
- The user asks what a hot `node` process actually was.
- The user wants to keep a background watcher installed and only log on real spikes.
- WindowServer remains high and the user wants evidence correlating it with foreground apps, visible apps, and display configuration.

## Boundaries

- macOS only. This skill depends on `launchctl` and `sample`.
- Building the daemon requires a Rust toolchain with `cargo`; the lifecycle script caches a release binary under `~/.cache/watch-hot-node/`.
- Do not claim a root cause from CPU alone. Read `parent-chain.txt`, `cwd.txt`, and `sample.txt` together.
- WindowServer CPU cannot be attributed exactly to one client from `ps`. Treat repeated foreground/visible-app correlations as evidence, not proof.
- A failed WindowServer `sample` can be a macOS permission boundary; the system and graphics context files remain useful.
- Prefer the bundled script over hand-editing the generated `LaunchAgent` plist.

## Workflow

### 1. Check Current State

Use the bundled script:

```bash
~/.codex/skills/watch-hot-node/scripts/watch_hot_node.sh --status
```

If you are not in Codex, use the same relative path inside that agent's installed `watch-hot-node` skill directory.

The status output includes the installed Rust daemon version.

### 2. Build The Rust Daemon

The install command builds automatically. To build explicitly:

```bash
~/.codex/skills/watch-hot-node/scripts/watch_hot_node.sh --build-daemon
```

The wrapper rebuilds only when `Cargo.toml`, `Cargo.lock`, or Rust sources change. It removes Cargo build artifacts after copying the release binary so the persistent cache stays small.

### 3. Install The Persistent Watcher

```bash
~/.codex/skills/watch-hot-node/scripts/watch_hot_node.sh --install-launch-agent
```

Useful environment overrides:

- `WATCH_CPU_THRESHOLD`
- `WATCH_WINDOWSERVER_ENABLED`
- `WATCH_WINDOWSERVER_THRESHOLD`
- `WATCH_INTERVAL_SEC`
- `WATCH_SAMPLE_DURATION_SEC`
- `WATCH_SAMPLE_INTERVAL_MS`
- `WATCH_COOLDOWN_SEC`
- `WATCH_MAX_EVENTS`
- `WATCH_MAX_LOG_MB`
- `WATCH_MAX_CAPTURE_WORKERS`
- `WATCH_VERBOSE`
- `WATCH_LOG_ROOT`

### 4. Reproduce The Spike

Let the workload run. The watcher stays quiet unless it captures a hot process.

Primary log:

```bash
tail -n 80 ~/.hermes/logs/node-hot-watch/watcher.log
```

### 5. Inspect The Latest Event

```bash
ls -1dt ~/.hermes/logs/node-hot-watch/event-* | head
sed -n '1,200p' ~/.hermes/logs/node-hot-watch/event-*/summary.txt
sed -n '1,120p' ~/.hermes/logs/node-hot-watch/event-*/parent-chain.txt
```

Read order for Node/Codex events:

1. `summary.txt` for timestamp, PID, cwd, and sample status
2. `event.json` for structured trigger and sample metadata
3. `parent-chain.txt` to see who launched it
4. `ps.txt` and `target-and-parent.txt` for command line and CPU snapshot
5. `sample.txt` for hot stack interpretation
6. `open-files.txt` and `network.txt` for I/O context

Read order for WindowServer events:

1. `summary.txt` for trigger CPU, threshold, and sample status
2. `system-processes.txt` to find apps consuming CPU at the same moment
3. `frontmost-app.txt` and `applications.txt` for graphical correlation
4. `displays.txt` for external displays, resolution, and refresh-rate context
5. `thermal.txt` and `system-summary.txt` for system pressure
6. `sample.txt` for compositor, display, or driver stack evidence when permitted

### 6. Run A One-Off Capture

If the hot process is still running now:

```bash
~/.codex/skills/watch-hot-node/scripts/watch_hot_node.sh --once
```

### 7. Stop The Watcher

```bash
~/.codex/skills/watch-hot-node/scripts/watch_hot_node.sh --stop
```

## Interpretation Hints

- A `cwd` under your app repo plus a parent like `npm run build` usually means the spike belongs to your workload, not the editor or agent host.
- Repeated `rollup`, `vite`, `tsc`, string encoding, or V8 scavenger frames usually point to compile or bundle work rather than network waits.
- Empty `network.txt` plus heavy `sample.txt` CPU stacks usually means compute-bound or GC-heavy work.
- Repeated WindowServer events with the same frontmost or visible app strengthen the attribution; one event is not enough.
- Node/Codex Rust CPU readings represent work during the configured interval. WindowServer events label their metric as `ps-decay-average` because macOS restricts its native CPU counters.
- High WindowServer plus low GPU-process CPU can still be window compositing, accessibility, screen capture, or high-frequency UI invalidation.
- `kernel_task` may rise during thermal management; do not report it as the original heat source without corroborating evidence.

## Bundled Resources

- `daemon/` contains the Rust watcher source and locked dependencies.
- `scripts/watch_hot_node.sh` builds the daemon and manages its LaunchAgent lifecycle.
