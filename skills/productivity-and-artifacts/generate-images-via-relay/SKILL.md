---
name: generate-images-via-relay
description: Generate images through an OpenAI-compatible image API exposed by AI Input or another relay, normally using the image-2 model, and save returned base64 or URL image data as local files. Use when the user asks to generate an image through a configured relay/provider, requests image-2, or wants to reuse a local config.toml image provider.
---

# Generate Images Via Relay

Use an existing AI Input or compatible relay as the image provider. Keep the workflow
provider-neutral: AI Input is one option, not a required dependency.

## Workflow

1. Read the existing provider configuration for its base URL, API-key environment
   variable or secret reference, and model name. Prefer the user's configured client or
   `config.toml`; preserve unrelated providers and never print credentials.
2. Send an OpenAI-compatible image-generation request to the provider's documented
   endpoint, commonly `<base-url>/images/generations`. Avoid adding a second `/v1`
   when the configured base URL already contains it.
3. Set `model` to `image-2` and pass the user's prompt without changing its intent.
   Include size, quality, background, or output format only when the relay documents
   those fields.
4. Parse the response as structured JSON. Decode `data[0].b64_json` when image bytes
   are returned inline, or download `data[0].url` when the relay returns a URL. When
   several images are returned, save each with a stable numeric suffix.
5. Validate that every saved file is a real image, inspect its dimensions, and present
   the resulting local file to the user.

Relay implementations can differ from the official API. Inspect a known working request
or the relay documentation before changing field names; do not guess a schema, silently
switch models, or claim success from an HTTP 200 response without validating the image.

## Safety

- Never expose API keys, authorization headers, or full credential-bearing config.
- Do not upload private reference images unless the user explicitly requests an edit.
- Report sanitized HTTP status and error details when the relay rejects a request.
- Preserve the original generated file unless the user asks for conversion or editing.
