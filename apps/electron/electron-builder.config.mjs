const hasAppleSigningIdentity = Boolean(process.env.CSC_LINK || process.env.CSC_NAME);
const hasNotarizationSecrets = Boolean(
  process.env.APPLE_API_KEY && process.env.APPLE_API_KEY_ID && process.env.APPLE_API_ISSUER,
);

/** @type {import('electron-builder').Configuration} */
const config = {
  appId: "com.skillctl.controlpanel",
  productName: "skillctl",
  directories: {
    output: "release",
  },
  files: ["out/**/*", "package.json"],
  npmRebuild: false,
  mac: {
    target: ["dmg", "zip"],
    category: "public.app-category.developer-tools",
    icon: "build/icon.png",
    hardenedRuntime: hasAppleSigningIdentity,
    gatekeeperAssess: false,
    identity: hasAppleSigningIdentity ? undefined : null,
    entitlements: hasAppleSigningIdentity ? "build/entitlements.mac.plist" : undefined,
    entitlementsInherit: hasAppleSigningIdentity ? "build/entitlements.mac.plist" : undefined,
  },
};

if (hasAppleSigningIdentity && hasNotarizationSecrets) {
  config.afterSign = "scripts/notarize.cjs";
}

export default config;
