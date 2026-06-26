# Submission Checklist

Use this checklist for both first submission and later updates.

## Package

- production build exists
- `manifest.json` is at the ZIP root
- popup / options / service worker / content scripts resolve correctly
- all referenced icons and static assets exist
- version number is intentionally set

## Permissions

- `permissions` are still needed
- `host_permissions` match real product behavior
- optional permissions are distinguished from always-on permissions
- no stale debug or migration permissions remain

## Privacy and disclosures

- remote APIs are identified
- authentication flows are identified
- user-generated content storage is identified
- sync behavior is identified
- privacy questionnaire answers match implementation
- privacy policy URL exists if needed

## Listing

- title is clear
- short description is specific
- long description matches shipped features
- screenshots reflect the current UI
- promo / marquee assets are present if the user wants richer storefront presentation
- support email or support URL is available

## Review risk scan

- no broken first-run path
- no dead buttons in screenshots or shipped UI
- no unsupported claims in copy
- no feature gated by undeclared permissions
- no hidden data transfer that is absent from disclosures

## Final output format

When auditing, separate:

- blockers
- policy risks
- missing assets
- optional polish
