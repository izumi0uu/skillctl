import type { SourceRegistryEntry } from "@skillctl/core";

export function httpUrl(value?: string | null): string | null {
  return value && /^https?:\/\//u.test(value) ? value : null;
}

// Resolve a skill's external source link. Only ever returns a real web URL —
// file:// / local:// provenance yields null so we never "open" a local path.
export function sourceUrl(
  entry?: Pick<SourceRegistryEntry, "upstream_source_url" | "upstream_repo"> | null,
): string | null {
  if (!entry) {
    return null;
  }
  const direct = httpUrl(entry.upstream_source_url) ?? httpUrl(entry.upstream_repo);
  if (direct) {
    return direct;
  }
  const repo = entry.upstream_repo;
  if (repo && !repo.includes("://") && /^[^/\s]+\/[^/\s]+/u.test(repo)) {
    return `https://github.com/${repo}`;
  }
  return null;
}
