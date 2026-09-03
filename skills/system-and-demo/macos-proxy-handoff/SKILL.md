---
name: macos-proxy-handoff
description: Diagnose and safely hand off connectivity between conflicting macOS proxy or VPN clients, especially 自由猫 and Clash Verge, when closing one leaves a privileged core, port, system proxy, DNS, or TUN route behind.
---

# macOS Proxy Handoff

Keep the currently working proxy online while diagnosing. Treat system proxy settings and TUN routes as shared singleton state: starting or stopping either app can disconnect the session that is performing the repair.

## Diagnose Without Disrupting Connectivity

Establish which application is carrying the current connection before changing anything:

- Identify GUI, core, and privileged-helper processes separately. A persistent Clash Verge helper is not the same as a running `verge-mihomo` core.
- Inspect listening ports, `scutil --proxy`, active `utun` interfaces, and the route to a public IP.
- Read only relevant configuration keys such as mixed port, system-proxy enablement, TUN enablement, auto-run, and minimize-on-exit.
- Search logs for narrowly scoped signatures such as `address already in use` and `permission denied`. Do not print subscription URLs, query strings, access tokens, node credentials, complete preferences, or complete process environments.

Common independent conflicts are:

1. Both cores bind the same local mixed port, commonly `127.0.0.1:7890`.
2. Closing a window minimizes the app while its privileged core remains alive.
3. Both apps update the one macOS system-proxy configuration.
4. Both apps install TUN routes or use the same fake-IP range.
5. A root-launched core leaves user-readable state owned by root.

Do not blame a privileged helper merely because it is persistent. Confirm that it owns a proxy port, core child, route, or relevant file before treating it as the conflict.

## Prepare A Stable Two-App Layout

Prefer these invariants when the user must keep both apps:

- Give the cores different local ports. The bundled handoff scripts assume 自由猫 uses `7890` and Clash Verge uses `7891`; override `FREECAT_PORT` or `CLASH_PORT` when needed.
- Allow only one app to own TUN at a time. For the bundled 自由猫/Clash layout, keep Clash Verge TUN disabled and let it use the macOS system proxy.
- Configure the target app before stopping the source app. Static configuration work must not require a live switch.
- Use the app's Quit action, not window close. Wait for both GUI and core to disappear before starting the other app.
- Do not perform the first live handoff from a remote conversation that depends on the source proxy. Install a local script, explain its rollback behavior, and let the user trigger it locally.

For Clash Verge, verify its persistent configuration rather than editing only a generated runtime file. Back up non-secret configuration before changing it, then keep the persistent port, generated configuration, and merge override coherent. Never include profiles, subscription URLs, tokens, or user-specific absolute home paths in a public artifact.

## Install The Handoff Commands

The scripts are self-contained so they can be copied to the user's Desktop without a shared runtime file:

- `scripts/switch-to-clash-verge.command`
- `scripts/switch-to-freecat.command`

Copy only after adapting ports or app locations when the defaults do not match. Preserve executable mode. The scripts accept these optional environment variables:

- `FREECAT_APP` and `CLASH_APP`
- `FREECAT_BUNDLE_ID` and `CLASH_BUNDLE_ID`
- `FREECAT_PORT` and `CLASH_PORT`
- `CLASH_CONFIG`
- `PROXY_HEALTH_URL`
- `PROXY_HANDOFF_DRY_RUN=1` for a non-mutating preflight

The target must satisfy three checks before success is reported:

1. Its local proxy port is listening.
2. macOS reports the system HTTP proxy enabled on that port.
3. An HTTPS request through that explicit local proxy returns HTTP 200 or 204.

If target startup or any health check fails, the scripts quit the failed target and reopen the source app. This rollback reduces the chance of a stranded offline state; it cannot provide zero-second handoff because the two GUI applications do not expose a transactional ownership protocol for macOS proxy and TUN state.

## Validation

Before delivery:

```bash
zsh -n scripts/switch-to-clash-verge.command
zsh -n scripts/switch-to-freecat.command
PROXY_HANDOFF_DRY_RUN=1 scripts/switch-to-clash-verge.command
PROXY_HANDOFF_DRY_RUN=1 scripts/switch-to-freecat.command
```

Run the live handoff only with explicit approval from the person at the Mac. If the active conversation depends on that proxy, provide the commands first and stop before live execution.

## Boundaries

- Do not force-kill a root core after the app rejects a quit request. Preserve the current connection and ask the user to confirm the app's own exit dialog.
- Do not enable both TUN implementations as a test.
- Do not remove Clash Verge's privileged helper just to stop the core; it is a normal service component.
- Do not promise seamless zero-downtime switching. A router-level proxy, a separate VPN/exit node, or another independent path is required for a true always-connected fallback.
- Do not replace the user's GUI workflow with raw core daemons unless the user explicitly requests a headless design and accepts losing GUI-managed updates and lifecycle behavior.
