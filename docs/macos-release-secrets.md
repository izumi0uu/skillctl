# macOS Release Secrets

This page is the operational checklist for turning on signed + notarized macOS releases in GitHub Actions.

The release workflow reads these six GitHub Actions secrets:

- `APPLE_CERTIFICATE_P12_BASE64`
- `APPLE_CERTIFICATE_PASSWORD`
- `APPLE_TEAM_ID`
- `APPLE_API_KEY_BASE64`
- `APPLE_API_KEY_ID`
- `APPLE_API_ISSUER`

If all six are present, `.github/workflows/release-mac.yml` signs and notarizes automatically. If any are missing, the workflow still builds unsigned `.dmg` + `.zip` artifacts.

## 1. Export the Developer ID Application certificate

You need a certificate named like `Developer ID Application: Your Name (TEAMID)` in macOS Keychain Access.

Export it as a password-protected `.p12`:

1. Open `Keychain Access`
2. Find the `Developer ID Application` certificate
3. Right-click it
4. Choose `Export`
5. Save as `developer-id-application.p12`
6. Set an export password

Convert it to base64:

```bash
base64 -i developer-id-application.p12 | pbcopy
```

Create these secrets in GitHub:

- `APPLE_CERTIFICATE_P12_BASE64`: the base64 output
- `APPLE_CERTIFICATE_PASSWORD`: the `.p12` export password
- `APPLE_TEAM_ID`: your Apple Developer Team ID

## 2. Create an App Store Connect API key

In App Store Connect:

1. Open `Users and Access`
2. Open the `Integrations` tab
3. Open `App Store Connect API`
4. Create a key with access to notarization
5. Download the `.p8` file once

Convert it to base64:

```bash
base64 -i AuthKey_ABC123XYZ.p8 | pbcopy
```

Create these secrets in GitHub:

- `APPLE_API_KEY_BASE64`: the base64 output
- `APPLE_API_KEY_ID`: the key ID, for example `ABC123XYZ`
- `APPLE_API_ISSUER`: the issuer UUID shown in App Store Connect

## 3. Add the secrets to GitHub

Repository path:

1. GitHub repo
2. `Settings`
3. `Secrets and variables`
4. `Actions`
5. `New repository secret`

Add all six secrets exactly with the names above.

## 4. Smoke test the signed release path

After secrets are configured:

1. Run the `Release macOS app` workflow manually from GitHub Actions, or
2. Push a version tag such as `v0.2.0`

Expected result:

- The workflow prepares signing assets
- The build step signs the app
- Notarization runs in `afterSign`
- The GitHub release gets `.dmg` and `.zip` attachments

## 5. Quick failure map

- `skipped macOS code signing`: one or more signing secrets are missing
- `notarize` authentication error: API key ID / issuer / `.p8` content mismatch
- certificate import / identity errors: `.p12` content or password mismatch
- Gatekeeper still warns after release: build was unsigned, notarization failed, or the downloaded app still has quarantine metadata
