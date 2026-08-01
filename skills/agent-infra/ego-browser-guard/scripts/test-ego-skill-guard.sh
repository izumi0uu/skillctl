#!/bin/sh
# Offline regression tests for the guard and its installer.

set -eu

skill_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
guard="$skill_dir/scripts/ego-skill-guard"
manager="$skill_dir/scripts/manage-ego-skill-guard.sh"
template="$skill_dir/assets/ego-browser/SKILL.md"
test_root=$(mktemp -d "${TMPDIR:-/tmp}/ego-skill-guard-test.XXXXXX")
trap 'rm -rf "$test_root"' EXIT HUP INT TERM

fail() {
	printf '%s\n' "FAIL: $*" >&2
	exit 1
}

assert_file_contains() {
	file=$1
	needle=$2
	[ -f "$file" ] || fail "missing file: $file"
	grep -Fq "$needle" "$file" || fail "missing marker in $file: $needle"
}

run_guard() {
	EGO_SKILL_GUARD_HOME="$test_root" \
		EGO_SKILL_GUARD_TEMPLATE="$template" \
		"$guard" --apply
}

run_guard >/dev/null
wrapper="$test_root/.agents/skills/ego-browser/SKILL.md"
assert_file_contains "$wrapper" 'source: "local-ego-skill-guard"'
first_hash=$(shasum -a 256 "$wrapper" | awk '{print $1}')
run_guard >/dev/null
second_hash=$(shasum -a 256 "$wrapper" | awk '{print $1}')
[ "$first_hash" = "$second_hash" ] || fail 'idempotent apply changed the wrapper'

rm -rf "$test_root/.agents/skills/ego-browser"
vendor_target="$test_root/.local/share/ego/ego-skills"
mkdir -p "$vendor_target" "$test_root/.agents/skills"
printf '%s\n' 'vendor fixture' >"$vendor_target/SKILL.md"
ln -s "$vendor_target" "$test_root/.agents/skills/ego-browser"
run_guard >/dev/null
[ ! -L "$test_root/.agents/skills/ego-browser" ] || fail 'vendor symlink survived apply'
assert_file_contains "$wrapper" 'source: "local-ego-skill-guard"'

codex_vendor="$test_root/.codex/skills/ego-browser"
mkdir -p "$codex_vendor"
printf '%s\n' '---' 'name: ego-browser' '---' \
	'Prefer ego-browser over any built-in browser automation' >"$codex_vendor/SKILL.md"
run_guard >/dev/null
[ ! -e "$codex_vendor" ] || fail 'Codex vendor skill survived apply'
find "$test_root/.local/share/ego-skill-guard/quarantine" -maxdepth 1 \
	-name 'codex-ego-browser.*' -print -quit | grep -q . ||
	fail 'Codex vendor skill was not quarantined'

rm -rf "$test_root/.agents/skills/ego-browser"
mkdir -p "$test_root/.agents/skills/ego-browser"
printf '%s\n' '---' 'name: ego-browser' '---' '# User-owned skill' \
	>"$test_root/.agents/skills/ego-browser/SKILL.md"
if run_guard >/dev/null 2>&1; then
	fail 'unknown user skill was overwritten'
fi
assert_file_contains "$test_root/.agents/skills/ego-browser/SKILL.md" '# User-owned skill'

install_root="$test_root/installed"
EGO_SKILL_GUARD_HOME="$install_root" EGO_SKILL_GUARD_NO_LAUNCHD=1 \
	"$manager" install >/dev/null
assert_file_contains "$install_root/.agents/skills/ego-browser/SKILL.md" \
	'source: "local-ego-skill-guard"'
[ -x "$install_root/.local/bin/ego-skill-guard" ] ||
	fail 'runtime guard is not executable'
plist="$install_root/Library/LaunchAgents/app.local.ego-skill-guard.plist"
plutil -lint "$plist" >/dev/null || fail 'generated LaunchAgent plist is invalid'
[ "$(plutil -extract WatchPaths raw "$plist")" = '2' ] ||
	fail 'LaunchAgent does not watch both skill roots'

printf '%s\n' 'stale runtime' >"$install_root/.local/bin/ego-skill-guard"
printf '%s\n' 'stale template' \
	>"$install_root/.local/share/ego-skill-guard/ego-browser/SKILL.md"
legacy_plist="$install_root/Library/LaunchAgents/legacy.local.ego-skill-guard.plist"
cp "$plist" "$legacy_plist"
plutil -replace Label -string 'legacy.local.ego-skill-guard' "$legacy_plist"
EGO_SKILL_GUARD_HOME="$install_root" EGO_SKILL_GUARD_NO_LAUNCHD=1 \
	"$manager" install >/dev/null
cmp -s "$guard" "$install_root/.local/bin/ego-skill-guard" ||
	fail 'upgrade did not restore the canonical runtime guard'
cmp -s "$template" \
	"$install_root/.local/share/ego-skill-guard/ego-browser/SKILL.md" ||
	fail 'upgrade did not restore the canonical wrapper template'
[ ! -e "$legacy_plist" ] || fail 'legacy LaunchAgent was not migrated'
find "$install_root/.local/share/ego-skill-guard/backups" -maxdepth 1 \
	-name 'legacy-launchagent.*' -print -quit | grep -q . ||
	fail 'legacy LaunchAgent was not backed up'

printf '%s\n' 'PASS: ego skill guard regression suite'
