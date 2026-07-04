# Title Policy

## Good Titles

- Describe the durable job of the session.
- Prefer 4-12 Chinese characters or 2-7 English words.
- Use domain nouns when helpful: `Billing Claim Cleanup`, `Prompt Versioning`, `Session Naming Rescan`.
- Use phase words only when they distinguish related sessions: `Plan`, `Execution`, `Verification`, `Rescan`, `Recovery`.
- Add numeric suffixes only for genuinely repeated responsibilities.

## Bad Titles

Avoid titles that only describe the last prompt or workflow wrapper:

- `continue`
- `start implementation`
- `help me check`
- `$ralph`
- `$ralplan`
- `debug`
- `fix`
- `review`
- `new chat`
- `untitled`

## Deduplication

Normalize candidate titles by lowercasing, trimming whitespace, removing trailing numeric suffixes, and collapsing punctuation. Then:

- If the normalized responsibility is the same, number repeated titles in stable order.
- If phase or artifact differs, prefer a phase-specific title instead of numbering.
- Do not number titles that are already unique after meaningful phase words are kept.

Examples:

```text
Session Batch Naming
Session Batch Naming 2
Session Batch Naming 3

Prompt Versioning Plan
Prompt Versioning Execution
Prompt Versioning Audit
```

## Keep Existing Titles

Keep an existing title when it is concise, specific, and not one of the generic titles above. Rename only generic, duplicated, misleading, unsafe, or explicitly requested titles.

## Sensitive Content

Never include:

- people names from clinical or customer data
- tokens, keys, secret-looking strings, or private environment values
- complete local paths unless the path itself is the task subject
- raw error stacks or command output
- raw prompt text, model responses, or clinical payload snippets
