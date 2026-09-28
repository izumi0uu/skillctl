#!/usr/bin/env python3
"""Install the terminal guards without changing browser preferences or credentials."""
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys

MARKER = b'# Managed by browser-incognito-guard'
BROWSERS = {
    'chrome': {
        'BUNDLE_ID': 'com.google.Chrome',
        'KEYCHAIN_SERVICE': 'com.idah.chrome.incognito-guard',
        'APP_PATH': '/Applications/Google Chrome.app',
        'PROCESS_NAME': 'Google Chrome',
        'APP_NAME': 'Google Chrome',
        'COMMAND': 'chrome-guard',
    },
    'ego': {
        'BUNDLE_ID': 'com.citrolabs.ego.lite',
        'KEYCHAIN_SERVICE': 'com.idah.ego-lite.incognito-guard',
        'APP_PATH': '/Applications/ego lite.app',
        'PROCESS_NAME': 'ego lite',
        'APP_NAME': 'Ego Lite',
        'COMMAND': 'ego-guard',
    },
}
ASSETS = Path(__file__).resolve().parent.parent / 'assets'


def payloads(browser: str, existing_browsers: tuple[str, ...] = ()) -> dict[str, bytes]:
    selected = list(BROWSERS) if browser == 'all' else [browser]
    routes = {BROWSERS[name]['BUNDLE_ID']: BROWSERS[name]['COMMAND']
              for name in BROWSERS if name in selected or name in existing_browsers}
    wrapper = (ASSETS / 'defaults.py.in').read_text().replace('__GUARDS__', repr(routes))
    result = {'defaults': wrapper.encode()}
    for name in selected:
        config = BROWSERS[name]
        source = (ASSETS / 'guard.py.in').read_text()
        for key, value in config.items():
            source = source.replace('__' + key + '__', value)
        result[config['COMMAND']] = source.encode()
    return result


def install(home: Path, browser: str, replace_existing: bool = False) -> list[Path]:
    destination = home / '.local/bin'
    existing = tuple(name for name, config in BROWSERS.items()
                     if (destination / config['COMMAND']).is_file())
    files = payloads(browser, existing)
    # Preflight every target before writing any of them.
    for name, content in files.items():
        target = destination / name
        if target.is_symlink():
            raise RuntimeError(f'Refusing symlink target: {target}')
        if target.exists() and target.read_bytes() != content:
            if MARKER not in target.read_bytes() and not replace_existing:
                raise RuntimeError(f'Existing unmanaged file: {target}; inspect it before using --replace-existing')
    destination.mkdir(parents=True, exist_ok=True)
    backup = home / '.local/share/browser-incognito-guard/backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    changed = []
    for name, content in files.items():
        target = destination / name
        if target.exists() and target.read_bytes() == content:
            target.chmod(0o700)
            continue
        if target.exists():
            backup.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(target, backup / name)
        temporary = destination / ('.' + name + '.incognito-install')
        # Exclusive creation prevents following an existing temporary symlink.
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        changed.append(target)
    if backup.exists():
        print(f'Backup: {backup}')
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', choices=['chrome', 'ego', 'all'], default='chrome')
    parser.add_argument('--home', type=Path, default=Path.home(), help='Override destination home for isolated testing')
    parser.add_argument('--replace-existing', action='store_true', help='Back up and replace reviewed unmanaged command files')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('The guard requires macOS.')
    try:
        for path in install(args.home.resolve(), args.browser, args.replace_existing):
            print(f'Installed: {path}')
    except (OSError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print('Keep ~/.local/bin before /usr/bin in PATH; set the code interactively, then lock when ready.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
