---
name: chrome-web-store-publish
description: Use when the user wants to prepare, audit, package, submit, or update a Chrome extension in the Chrome Web Store, including store listing assets, privacy disclosures, permissions review, ZIP packaging, and release readiness.
---

# Chrome Web Store Publish

Use this skill when the task is to get a Chrome extension ready for Chrome Web Store submission or update.

This skill is for the practical publishing loop:

- review extension packaging readiness
- audit manifest, permissions, and disclosure-sensitive behavior
- verify required store assets and listing copy
- build the upload ZIP correctly
- cross-check the Chrome Web Store dashboard steps
- catch common review blockers before submission

## What This Skill Owns

- pre-submission audit for MV3 Chrome extensions
- update submissions for an already-listed extension
- store listing preparation:
  - title
  - short and long description
  - screenshots
  - promo / marquee assets
  - privacy policy requirements
  - support links
- packaging rules for the upload ZIP
- Chrome Web Store review readiness

## Default Operating Order

1. Inspect the extension build output and `manifest.json`.
2. Check whether the extension behavior matches the requested permissions and host permissions.
3. Check whether remote services, authentication, sync, analytics, or user-generated content affect privacy disclosures.
4. Verify store assets and listing copy against the current Chrome Web Store requirements.
5. Build or verify the upload ZIP:
   - ZIP root must contain `manifest.json`
   - do not ZIP the parent folder
6. Prepare a final submission checklist with blockers vs ready items.

## Canonical Audit Areas

### 1. Technical package readiness

Always verify:

- `manifest_version` is `3`
- all icons referenced by `manifest.json` exist
- `options_page`, popup, service worker, and content script paths exist
- the packaged build is self-contained
- the ZIP root directly contains `manifest.json`

Flag as blockers:

- missing assets referenced by the manifest
- permissions that no longer match actual behavior
- broken options / popup / background entrypoints
- dev-only files accidentally packaged as runtime requirements

### 2. Permissions and review surface

Review these fields carefully:

- `permissions`
- `host_permissions`
- `optional_permissions`
- OAuth / identity behavior
- remote sync or third-party API behavior

For each permission, explain:

- what user-facing feature requires it
- whether the feature is core or optional
- whether the store listing and privacy answers need to mention it

Prefer tightening permissions if the code no longer needs them.

### 3. Privacy and disclosure surface

Check whether the extension:

- collects personal data
- authenticates to third-party services
- stores user-generated notes, tags, or synced content
- sends data to GitHub, Gist, or any other remote service
- tracks analytics, telemetry, or error reporting

If any of these are true, verify that the Chrome Web Store privacy questionnaire and any privacy policy text are consistent with the implementation.

### 4. Store listing assets

Verify the existence and suitability of:

- store icon
- screenshots
- promo / marquee assets if used
- readable extension description copy
- support URL / support email
- privacy policy URL if required

Read `references/official-links.md` for official Google sources before giving size guidance or listing requirements.

## How To Work

### If the user wants a readiness audit

Return:

- `Ready`
- `Needs fixes before submission`
- `Ready with non-blocking polish`

Then list:

- blockers
- policy / disclosure risks
- missing store assets
- packaging status

### If the user wants help packaging

Do this:

1. identify the extension build directory
2. verify `manifest.json` at the ZIP root
3. create or validate the upload ZIP
4. summarize exactly which folder/file should be uploaded

### If the user wants help filling the Chrome Web Store dashboard

Guide them through:

1. upload package
2. store listing
3. privacy / permissions disclosures
4. distribution / visibility
5. final review checklist

Do not invent current dashboard labels from memory when a precise answer matters. Use the official links in `references/official-links.md` when needed.

## Common Review Risks

- permissions requested more broadly than the shipped feature set
- host permissions that are not explained in listing copy
- no privacy policy when remote sync or personal data storage makes one advisable or required
- screenshots that do not reflect the current UI
- ZIP created from the parent directory instead of the extension root
- unpublished or broken onboarding that leaves first-run behavior confusing
- claims in the listing that the product does not actually support

## When To Read References

- Read `references/official-links.md` when you need current official Google guidance or exact document links.
- Read `references/submission-checklist.md` when you need a structured pre-submit or pre-update audit.

## Success Condition

The task is complete only when:

- the extension package is structurally valid for upload
- permission and privacy disclosures have been checked against actual behavior
- listing assets and copy have been reviewed
- submission blockers are clearly separated from polish
- the user has an actionable upload / submit path, not just general advice
