---
name: ego-browser
description: >
  Use Ego Lite only when the user explicitly asks to use Ego Lite or
  ego-browser, or when the task requires an authenticated or session-bound
  interactive UI, form submission, browser-only visual verification, or web-app
  testing. Public static content, including JavaScript-rendered pages, must use
  a connector, CLI, API, or direct HTTP first and must not trigger Ego Lite
  merely for extraction or navigation.
metadata:
  source: "local-ego-skill-guard"
  version: "1.1.0"
---

# Ego Lite On Demand

When this skill is selected, use the `ego-browser` command available on the
PATH. For its browser-operation reference, read the vendor documentation at
`~/.local/share/ego/ego-skills/SKILL.md` when it exists.

Before starting Ego Lite, identify the qualifying condition in the task. Do
not start it for public content merely to navigate, scrape, search, or extract
text. Use it only after establishing that the task needs authenticated browser
state, a browser-only interaction, form submission, Web App testing, or visual
verification that non-browser tools cannot provide.

If a connector, CLI, API, or direct HTTP request can complete the work without
losing required session state or visual evidence, use that narrower tool.
