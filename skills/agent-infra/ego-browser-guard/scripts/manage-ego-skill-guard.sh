#!/bin/sh
# Install and manage the temporary macOS Ego skill guard.

set -eu

usage() {
	printf '%s\n' "usage: manage-ego-skill-guard.sh {install|status|apply|uninstall}" >&2
	exit 2
}

command_name=${1:-}
case "$command_name" in
	install|status|apply|uninstall) ;;
	*) usage ;;
esac

skill_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
guard_home=${EGO_SKILL_GUARD_HOME:-"$HOME"}
data_root="$guard_home/.local/share/ego-skill-guard"
runtime_guard="$guard_home/.local/bin/ego-skill-guard"
runtime_template="$data_root/ego-browser/SKILL.md"
launch_agents="$guard_home/Library/LaunchAgents"
label='app.local.ego-skill-guard'
plist="$launch_agents/$label.plist"
log_path="$data_root/launchd.log"
source_guard="$skill_dir/scripts/ego-skill-guard"
source_template="$skill_dir/assets/ego-browser/SKILL.md"
backup_root="$data_root/backups"
launch_domain="gui/$(id -u)"
launchd_enabled=true

if [ "${EGO_SKILL_GUARD_NO_LAUNCHD:-0}" = '1' ] || [ "$guard_home" != "$HOME" ]; then
	launchd_enabled=false
fi

backup_file() {
	backup_path=$1
	backup_label=$2
	[ -e "$backup_path" ] || [ -L "$backup_path" ] || return 0
	mkdir -p "$backup_root"
	backup_stamp=$(date +%Y%m%d%H%M%S)
	backup_destination="$backup_root/$backup_label.$backup_stamp.$$"
	mv "$backup_path" "$backup_destination"
	printf '%s\n' "backed up $backup_path -> $backup_destination"
}

install_file() {
	install_source=$1
	install_destination=$2
	install_mode=$3
	install_label=$4
	mkdir -p "$(dirname -- "$install_destination")"
	if [ -e "$install_destination" ] && ! cmp -s "$install_source" "$install_destination"; then
		backup_file "$install_destination" "$install_label"
	fi
	if ! cmp -s "$install_source" "$install_destination" 2>/dev/null; then
		install -m "$install_mode" "$install_source" "$install_destination"
		printf '%s\n' "installed $install_destination"
	else
		chmod "$install_mode" "$install_destination"
	fi
}

write_plist() {
	temporary="$plist.tmp.$$"
	rm -f "$temporary"
	plutil -create xml1 "$temporary"
	plutil -insert Label -string "$label" "$temporary"
	plutil -insert ProgramArguments -array "$temporary"
	plutil -insert ProgramArguments.0 -string "$runtime_guard" "$temporary"
	plutil -insert ProgramArguments.1 -string '--apply' "$temporary"
	plutil -insert RunAtLoad -bool true "$temporary"
	plutil -insert WatchPaths -array "$temporary"
	plutil -insert WatchPaths.0 -string "$guard_home/.agents/skills" "$temporary"
	plutil -insert WatchPaths.1 -string "$guard_home/.codex/skills" "$temporary"
	plutil -insert ThrottleInterval -integer 2 "$temporary"
	plutil -insert StandardOutPath -string "$log_path" "$temporary"
	plutil -insert StandardErrorPath -string "$log_path" "$temporary"
	plutil -lint "$temporary" >/dev/null
	if [ -e "$plist" ] && ! cmp -s "$temporary" "$plist"; then
		backup_file "$plist" 'launchagent'
	fi
	if ! cmp -s "$temporary" "$plist" 2>/dev/null; then
		mv "$temporary" "$plist"
		chmod 0644 "$plist"
		printf '%s\n' "installed $plist"
	else
		rm -f "$temporary"
	fi
}

launchctl_bootout() {
	target_plist=$1
	$launchd_enabled || return 0
	[ -f "$target_plist" ] || return 0
	launchctl bootout "$launch_domain" "$target_plist" >/dev/null 2>&1 || true
}

migrate_legacy_plists() {
	for legacy_candidate in "$launch_agents"/*.ego-skill-guard.plist; do
		[ -f "$legacy_candidate" ] || continue
		[ "$legacy_candidate" != "$plist" ] || continue
		legacy_program=$(plutil -extract ProgramArguments.0 raw "$legacy_candidate" 2>/dev/null || true)
		if [ "$legacy_program" = "$runtime_guard" ]; then
			launchctl_bootout "$legacy_candidate"
			backup_file "$legacy_candidate" 'legacy-launchagent'
		else
			printf '%s\n' "warning: preserving unrelated LaunchAgent: $legacy_candidate" >&2
		fi
	done
}

install_guard() {
	[ "$(uname -s)" = 'Darwin' ] || {
		printf '%s\n' 'error: LaunchAgent installation requires macOS' >&2
		exit 1
	}
	[ -f "$source_guard" ] && [ -f "$source_template" ] || {
		printf '%s\n' 'error: canonical guard files are incomplete' >&2
		exit 1
	}

	mkdir -p "$data_root" "$launch_agents" "$guard_home/.agents/skills" "$guard_home/.codex/skills"
	chmod 0700 "$data_root"
	install_file "$source_guard" "$runtime_guard" 0755 'runtime-guard'
	install_file "$source_template" "$runtime_template" 0644 'wrapper-template'

	launchctl_bootout "$plist"
	migrate_legacy_plists
	write_plist

	EGO_SKILL_GUARD_HOME="$guard_home" \
		EGO_SKILL_GUARD_TEMPLATE="$runtime_template" \
		"$runtime_guard" --apply

	if $launchd_enabled; then
		launchctl bootstrap "$launch_domain" "$plist"
		launchctl kickstart -k "$launch_domain/$label"
	fi
	printf '%s\n' 'ego skill guard installed'
}

status_guard() {
	if [ -x "$runtime_guard" ]; then
		EGO_SKILL_GUARD_HOME="$guard_home" \
			EGO_SKILL_GUARD_TEMPLATE="$runtime_template" \
			"$runtime_guard" --status
	else
		printf '%s\n' 'runtime guard: absent'
	fi
	if [ -f "$plist" ]; then
		printf '%s\n' "LaunchAgent plist: present ($plist)"
	else
		printf '%s\n' 'LaunchAgent plist: absent'
	fi
	if $launchd_enabled && launchctl print "$launch_domain/$label" >/dev/null 2>&1; then
		printf '%s\n' 'LaunchAgent state: loaded'
	elif $launchd_enabled; then
		printf '%s\n' 'LaunchAgent state: not loaded'
	else
		printf '%s\n' 'LaunchAgent state: not checked'
	fi
}

apply_guard() {
	[ -x "$runtime_guard" ] || {
		printf '%s\n' "error: runtime guard not installed: $runtime_guard" >&2
		exit 1
	}
	EGO_SKILL_GUARD_HOME="$guard_home" \
		EGO_SKILL_GUARD_TEMPLATE="$runtime_template" \
		"$runtime_guard" --apply
}

uninstall_guard() {
	launchctl_bootout "$plist"
	if [ -f "$guard_home/.agents/skills/ego-browser/SKILL.md" ] &&
		grep -Fq 'source: "local-ego-skill-guard"' "$guard_home/.agents/skills/ego-browser/SKILL.md"; then
		backup_file "$guard_home/.agents/skills/ego-browser" 'uninstalled-wrapper'
	fi
	if [ -e "$plist" ]; then
		backup_file "$plist" 'uninstalled-launchagent'
	fi
	if [ -e "$runtime_guard" ]; then
		backup_file "$runtime_guard" 'uninstalled-runtime-guard'
	fi
	if [ -e "$runtime_template" ]; then
		backup_file "$runtime_template" 'uninstalled-wrapper-template'
	fi
	printf '%s\n' "guard disabled; backups retained under $backup_root"
}

case "$command_name" in
	install) install_guard ;;
	status) status_guard ;;
	apply) apply_guard ;;
	uninstall) uninstall_guard ;;
esac
