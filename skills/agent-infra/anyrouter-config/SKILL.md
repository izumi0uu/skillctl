---
name: anyrouter-config
description: Configure, verify, and debug an AnyRouter gateway for Claude Code or cc switch. Use when the user wants to add an AnyRouter provider, wire `ANTHROPIC_BASE_URL` plus token auth, test `/v1/models` or `/v1/messages`, diagnose 400/401/429/503 gateway failures, or find at least one model that returns a real assistant response.
---

# AnyRouter Config

## Overview

Use this skill to configure an AnyRouter-backed Claude gateway, validate the auth path, and drive the setup all the way to a successful model reply.

Prefer this skill when the request involves `cc switch`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, Anthropic-compatible relay endpoints, or model-by-model probing for Claude availability.

## Inputs

- `base_url`: the gateway root such as `https://example.com`
- `token`: the real gateway token
- `client`: `cc switch`, local `~/.claude/settings.json`, or both
- `target model`: optional; if omitted, probe available models and find a working default

If the user pastes a markdown link instead of a raw URL, strip the markdown wrapper first.

## Workflow

1. Normalize the gateway URL.
   - Use the root URL without a trailing slash.
   - Do not store `/v1/messages` as the base URL unless the gateway explicitly requires a full endpoint.
   - Test with `GET /v1/models` first.
2. Prove the auth scheme before editing configs.
   - Probe both:
     - `Authorization: Bearer <token>`
     - `x-api-key: <token>`
   - Keep only the scheme that returns a real model list or a model-specific error.
   - For Claude-compatible AnyRouter setups, `Bearer` is often the working path and maps naturally to `ANTHROPIC_AUTH_TOKEN`.
3. Configure the target client.
   - For `cc switch`, prefer a Claude custom provider with:
     - `ANTHROPIC_BASE_URL`
     - the working token env key
     - explicit default model envs
   - For local Claude, write the same envs into `~/.claude/settings.json`.
   - Remove or avoid stale `apiKeyHelper` settings when they interfere with third-party routing.
   - Preserve model-slot semantics:
     - `ANTHROPIC_MODEL` is the user's current default and may be a separate model such as `claude-fable-5`.
     - `ANTHROPIC_DEFAULT_OPUS_MODEL` should stay on a real Opus-family model when the gateway advertises one.
     - `ANTHROPIC_DEFAULT_SONNET_MODEL` should stay on a real Sonnet-family model when the gateway advertises one.
     - `ANTHROPIC_DEFAULT_HAIKU_MODEL` should stay on a real Haiku-family model.
   - Do not collapse Opus, Sonnet, and Haiku slots onto the same fallback model unless the user explicitly asks for that simplification.
4. Validate model discovery.
   - `GET /v1/models` must return `200` and a non-empty list.
   - Group the result into Claude, GPT, Gemini, and other families when reporting back.
5. Validate message completion.
   - Try `POST /v1/messages` with a tiny prompt such as `Reply with exactly: pong`.
   - If the gateway reports a 1M-context requirement, retry with `anthropic-beta: context-1m-2025-08-07` and/or `ANTHROPIC_BETAS=context-1m-2025-08-07`.
   - If an advanced model fails with `429` or `503`, do a short retry loop before declaring it unavailable.
     - Prefer 3 to 6 retries with small prompts.
     - Prefer testing both streaming and non-streaming if the user's real client uses streaming.
   - Distinguish "healthy default model" from "slot mapping".
     - It is fine for `ANTHROPIC_MODEL` to stay on a healthy default such as `claude-fable-5` or Haiku while the Opus and Sonnet slots still point to real Opus/Sonnet family models.
     - Do not rewrite the Opus/Sonnet slot mappings just because the first probe returned `503`.
6. Converge on a working default.
   - Once one model replies successfully, set it as the default model for the active client unless the user asked to preserve another default.
   - Report separately:
     - which model is the active default
     - which real models are bound to Opus/Sonnet/Haiku slots
     - which probes succeeded immediately
     - which probes only failed with queue-like `429` or transient `503`

## `cc switch` Notes

- The provider record and the UI pointer may both need updating.
- Check both:
  - the provider row in `~/.cc-switch/cc-switch.db`
  - `currentProviderClaude` in `~/.cc-switch/settings.json`
- If they disagree, make them consistent before claiming the switch is complete.

## Local Claude Notes

For `~/.claude/settings.json`, prefer a slot-preserving env shape such as:

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "sk-...",
    "ANTHROPIC_BASE_URL": "https://example.com",
    "ANTHROPIC_MODEL": "claude-fable-5",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-8",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-5-20250929",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5-20251001",
    "CLAUDE_CODE_SUBAGENT_MODEL": "claude-haiku-4-5-20251001",
    "ANTHROPIC_BETAS": "context-1m-2025-08-07"
  }
}
```

Use `ANTHROPIC_API_KEY` instead only if the probe proves the gateway expects `x-api-key`.

## Failure Patterns

- `401` or `未提供令牌`
  - Wrong auth header, missing token, or wrong env key.
- `400` asking to enable 1M context
  - Add `ANTHROPIC_BETAS=context-1m-2025-08-07` and retry.
- `400` saying a model is offline
  - Do not keep retrying that model; switch to another advertised model.
- `429` or `503 Service Unavailable`
  - Gateway path is likely correct; advanced models may be queued or transiently capacity-limited.
  - Retry the same model a few times before downgrading it in config.
  - Prefer keeping real Opus/Sonnet slot mappings even if the active default stays on a healthier fallback.

## Guardrails

- Never echo secrets back to the user unless explicitly asked.
- Back up `~/.cc-switch` and `~/.claude/settings.json` before edits.
- Do not claim the setup works until `/v1/messages` returns a real assistant response.
- If the user asks for “ping通”, treat `/v1/models` as insufficient; require a successful message completion.
- When the user asks for real Opus or Sonnet support, avoid "helpful" remapping of those slots to Haiku unless the user explicitly prefers reliability over slot fidelity.

## Bundled Resources

- Read `references/troubleshooting.md` when you need a compact checklist for probing auth, 1M beta, and model fallback decisions.
