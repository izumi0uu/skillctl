---
name: browser-incognito-guard
description: Install, maintain, or troubleshoot the macOS terminal passcode guard for Google Chrome and Ego Lite incognito mode, including defaults interception, 50-digit codes, cooldowns, and temporary unlocked sessions.
---

# Browser Incognito Guard

Use this skill for the local incognito command guard. The separate `ego-browser-guard` skill manages agent skill selection and is unrelated to incognito policy.

## Install

Requires macOS, Python 3 on PATH, and the selected browser at its normal `/Applications` location. Work from this skill's directory. The installer defaults to Chrome; use `--browser ego` or `--browser all` when requested.

```bash
python3 scripts/test_guard.py
python3 scripts/install.py --browser chrome
```

The installer creates `~/.local/bin/chrome-guard` and a `defaults` wrapper. It installs `ego-guard` only when selected. Wrapper routes cover selected browsers and guards already present in the destination; other browser commands pass through. Existing unmanaged files cause a preflight failure: inspect their contents first, then use `--replace-existing` if replacing them is within the requested scope. Replaced files are backed up under `~/.local/share/browser-incognito-guard/backups/`.

Ensure `~/.local/bin` precedes `/usr/bin` in the user's shell PATH. Preserve other PATH entries and avoid adding duplicate shell configuration. Verify with `command -v defaults` and `command -v chrome-guard`. Installation itself does not configure a secret, change browser policies, or quit a browser.

Ask the user to set their secret in their own terminal; do not request or handle the code in chat:

```bash
chrome-guard set-code
chrome-guard status
```

The code must contain exactly 50 ASCII digits. Setup asks twice without echo. Only its SHA-256 digest is stored in macOS Keychain. Chrome and Ego have separate secrets and cooldowns. The `com.idah.*` Keychain service identifiers are retained for compatibility with the original local scripts; they are service names, not credentials or home paths.

## Operate

| Action | Chrome command | Effect |
| --- | --- | --- |
| Disable incognito | `chrome-guard lock` | Writes policy 1 and quits Chrome |
| Persistent enable | `defaults write com.google.Chrome IncognitoModeAvailability -int 0` | Runs the guard, then writes policy 0 after successful verification |
| Inspect | `chrome-guard status` | Reads the user policy and remaining cooldown |

For Ego use `ego-guard` and bundle ID `com.citrolabs.ego.lite`. Locking either browser may quit the running browser; save work first.

An unset code blocks the enable command and prints the appropriate `set-code` instruction. Verification requires a terminal and manual entry followed by Enter. It rejects bracketed paste, temporarily clears then restores the plain-text clipboard, and imposes a 30-minute cooldown after failed verification. Failure also writes policy 1 and attempts to quit the selected browser. Backspace is supported.

The command surface intentionally has no `unlock` operation. Keep the policy at `1` to disable incognito; enabling it requires the protected `defaults` wrapper and a successful gate verification.

The wrapper verifies policy writes unless they explicitly set integer `1` using `-int` or `-integer`. This includes `-integer 0`, untyped values, and forced-incognito value `2`. Deleting the policy or browser domain, importing the domain, and whole-domain writes also require verification because they can remove the restriction. Leading `-currentHost` and `-host <hostname>` options are handled. Unrelated keys and read commands pass through.

The explicit lock command writes policy `1` and quits the selected browser. A restart may be required for the browser to apply the policy.

## Verify And Troubleshoot

- Run `python3 scripts/test_guard.py` before shipping edits. Tests use temporary homes and mocks; they do not read real secrets, change policies, or quit browsers.
- `status` reports the user defaults value, not proof that the running browser applied it. After a user-requested policy change and browser restart, inspect the browser's effective policy page (`chrome://policy`) and incognito menu if behavior differs. Managed policies can override user preferences.
- If the wrapper is not selected, inspect shell aliases/functions and PATH order. A full `/usr/bin/defaults` path bypasses this wrapper.
- Do not validate by guessing a code: a failed live attempt changes policy and starts the cooldown.
- For rollback, restore only the relevant backed-up command files. Removing the wrapper does not reset browser policy or delete Keychain entries. Make those changes only when requested.

## Practical Limits

This is a voluntary terminal friction mechanism, not system access control. The wrapper guards policy changes addressed to the configured browser bundle IDs, including policy deletion and whole-domain replacement. Direct `/usr/bin/defaults`, preference-file paths or aliases instead of bundle IDs, other preference tools, script edits, and resetting the code can bypass it. Installing it does not disable incognito until `lock` runs. Whole-domain writes and imports conservatively require verification even when their contents would preserve the restriction.

Paste detection depends on terminal escape sequences and is not proof of physical typing. Clipboard restoration preserves plain text only; avoid live verification while rich clipboard content matters. No passwords, digests, cooldown state, or browser profiles belong in the skill repository.
