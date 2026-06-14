# AnyRouter Troubleshooting

## Minimal Probe Sequence

1. `GET /v1/models` with `Authorization: Bearer <token>`
2. `GET /v1/models` with `x-api-key: <token>`
3. Keep the scheme that returns `200`
4. `POST /v1/messages` with a tiny prompt
5. If the response asks for 1M context, retry with:
   - header: `anthropic-beta: context-1m-2025-08-07`
   - env: `ANTHROPIC_BETAS=context-1m-2025-08-07`
6. If an advanced Claude model returns `429` or `503`, retry it 3 to 6 times before treating it as unavailable
7. Keep active default health separate from slot mapping:
   - `ANTHROPIC_MODEL` may stay on a healthy model such as `claude-fable-5`
   - `ANTHROPIC_DEFAULT_OPUS_MODEL` should still point to a real Opus-family model
   - `ANTHROPIC_DEFAULT_SONNET_MODEL` should still point to a real Sonnet-family model
   - `ANTHROPIC_DEFAULT_HAIKU_MODEL` should still point to a real Haiku-family model

## Good Success Signal

Success is not:

- `GET /v1/models` returns `200`
- the model appears in the list

Success is:

- `POST /v1/messages` returns `200`
- response JSON contains `role: "assistant"`
- response `content` contains real text such as `pong`

## Common Recovery Moves

- Original default model returns `503`
  - Try a smaller or older healthy Claude model.
- Opus or Sonnet returns `503` on the first probe
  - Treat it as possibly queued or capacity-limited before rewriting slot mappings.
  - Keep the real family mapping unless repeated retries and the user's preference say otherwise.
- Gateway advertises a model that immediately says it is offline
  - Treat the model list as advisory, not guaranteed.
- `cc switch` row is correct but UI still shows official Claude
  - Sync `currentProviderClaude` in `~/.cc-switch/settings.json`.
