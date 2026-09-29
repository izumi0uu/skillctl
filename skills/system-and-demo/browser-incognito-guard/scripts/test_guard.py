import importlib.machinery
import importlib.util
import subprocess
import unittest
import tempfile
import contextlib
import io
import atexit
from pathlib import Path
from unittest.mock import patch

SCRIPT_ROOT = Path(__file__).resolve().parent
SANDBOX = tempfile.TemporaryDirectory()
atexit.register(SANDBOX.cleanup)
ROOT = Path(SANDBOX.name).resolve() / '.local/bin'
ROOT.mkdir(parents=True)
exec(compile((SCRIPT_ROOT / 'install.py').read_text(), str(SCRIPT_ROOT / 'install.py'), 'exec'), installer_scope := {'__name__': 'installer', '__file__': str(SCRIPT_ROOT / 'install.py')})
for name, content in installer_scope['payloads']('all').items():
    (ROOT / name).write_bytes(content)

def load(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(ROOT / filename))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module

wrapper = load('wrapper', 'defaults')
guard = load('guard', 'chrome-guard')

class GuardTests(unittest.TestCase):
    def test_routing_and_denial(self):
        for domain, name in wrapper.GUARDS.items():
            args = ['defaults', 'write', domain, 'IncognitoModeAvailability', '-int', '0']
            with self.subTest(domain=domain), patch.object(wrapper.sys, 'argv', args), patch.object(wrapper.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2)) as run, patch.object(wrapper.os, 'execv') as execute:
                self.assertEqual(wrapper.main(), 2)
                self.assertEqual(run.call_args.args[0], [str(ROOT / name), 'gate'])
                execute.assert_not_called()

    def test_policy_removal_and_equivalent_writes_require_verification(self):
        policy = 'IncognitoModeAvailability'
        for domain in wrapper.GUARDS:
            commands = [
                ['write', domain, policy, '-integer', '0'],
                ['write', domain, policy, '0'],
                ['write', domain, policy, '-int', '+0'],
                ['write', domain, policy, '-string', '0'],
                ['write', domain, policy, '-int', '2'],
                ['delete', domain, policy],
                ['delete', domain],
                ['write', domain, '{OtherSetting = 1;}'],
                ['import', domain, 'settings.plist'],
            ]
            for command in commands:
                for prefix in ([], ['-currentHost'], ['-host', 'localhost']):
                    args = ['defaults', *prefix, *command]
                    with self.subTest(args=args), patch.object(wrapper.sys, 'argv', args), patch.object(wrapper.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2)), patch.object(wrapper.os, 'execv') as execute:
                        self.assertEqual(wrapper.main(), 2)
                        execute.assert_not_called()

    def test_verified_policy_changes_preserve_original_arguments(self):
        for command in [
            ['write', 'com.google.Chrome', 'IncognitoModeAvailability', '-integer', '0'],
            ['delete', 'com.google.Chrome', 'IncognitoModeAvailability'],
        ]:
            args = ['defaults', *command]
            with self.subTest(args=args), patch.object(wrapper.sys, 'argv', args), patch.object(wrapper.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), patch.object(wrapper.os, 'execv') as execute:
                wrapper.main()
                execute.assert_called_once_with('/usr/bin/defaults', args)

    def test_lock_aliases_and_unrelated_settings_do_not_prompt(self):
        for command in [
            ['write', 'com.google.Chrome', 'IncognitoModeAvailability', '-integer', '1'],
            ['-currentHost', 'write', 'com.google.Chrome', 'IncognitoModeAvailability', '-int', '1'],
            ['write', 'com.google.Chrome', 'OtherSetting', '-int', '0'],
            ['delete', 'com.google.Chrome', 'OtherSetting'],
        ]:
            args = ['defaults', *command]
            with self.subTest(args=args), patch.object(wrapper.sys, 'argv', args), patch.object(wrapper.subprocess, 'run') as run, patch.object(wrapper.os, 'execv') as execute:
                wrapper.main()
                run.assert_not_called()
                execute.assert_called_once_with('/usr/bin/defaults', args)

    def test_verified_write(self):
        args = ['defaults', 'write', 'com.google.Chrome', 'IncognitoModeAvailability', '-int', '0']
        with patch.object(wrapper.sys, 'argv', args), patch.object(wrapper.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), patch.object(wrapper.os, 'execv') as execute:
            wrapper.main()
            execute.assert_called_once_with('/usr/bin/defaults', args)

    def test_other_commands_pass_through(self):
        for args in [[], ['read', 'com.google.Chrome'], ['write', 'com.google.Chrome', 'IncognitoModeAvailability', '-int', '1'], ['write', 'unrelated', 'x', '-int', '0']]:
            with self.subTest(args=args), patch.object(wrapper.sys, 'argv', ['defaults', *args]), patch.object(wrapper.subprocess, 'run') as run, patch.object(wrapper.os, 'execv') as execute:
                wrapper.main()
                run.assert_not_called()
                execute.assert_called_once_with('/usr/bin/defaults', ['defaults', *args])

    def test_unconfigured_fails_closed(self):
        with patch.object(guard, 'read_expected_digest', return_value=None), patch.object(guard, 'read_hash_tui') as tui, patch.object(guard, 'set_policy') as policy:
            self.assertEqual(guard.verify_gate(), 2)
            tui.assert_not_called()
            policy.assert_not_called()

    def test_cooldown_prevents_attempt(self):
        with patch.object(guard, 'read_expected_digest', return_value='a' * 64), patch.object(guard, 'cooldown_remaining', return_value=1800), patch.object(guard, 'read_hash_tui') as tui:
            self.assertEqual(guard.verify_gate(), 1)
            tui.assert_not_called()

    def test_failure_locks_chrome(self):
        with patch.object(guard, 'read_expected_digest', return_value='a' * 64), patch.object(guard, 'cooldown_remaining', return_value=0), patch.object(guard, 'read_hash_tui', return_value=False), patch.object(guard, 'set_lock_until') as cooldown, patch.object(guard, 'set_policy') as policy, patch.object(guard, 'app_running', return_value=False):
            self.assertEqual(guard.verify_gate(), 1)
            cooldown.assert_called_once()
            policy.assert_called_once_with(1)

    def test_success_clears_cooldown(self):
        with patch.object(guard, 'read_expected_digest', return_value='a' * 64), patch.object(guard, 'cooldown_remaining', return_value=0), patch.object(guard, 'read_hash_tui', return_value=True), patch.object(guard, 'clear_cooldown') as clear:
            self.assertEqual(guard.verify_gate(), 0)
            clear.assert_called_once()

    def test_browser_isolation(self):
        self.assertEqual(guard.BUNDLE_ID, 'com.google.Chrome')
        self.assertEqual(guard.KEYCHAIN_SERVICE, 'com.idah.chrome.incognito-guard')
        self.assertEqual(guard.LOCK_SERVICE, 'com.idah.chrome.incognito-guard.lock')
        self.assertNotIn('Ego Lite', (ROOT / 'chrome-guard').read_text())
        with patch.object(guard, 'run', return_value=subprocess.CompletedProcess([], 0)) as run:
            guard.set_policy(1)
            self.assertEqual(run.call_args.args[0], ['/usr/bin/defaults', 'write', 'com.google.Chrome', 'IncognitoModeAvailability', '-int', '1'])

    def test_secret_format(self):
        self.assertTrue(guard.is_valid_secret('1' * 50))
        for value in ['1' * 49, '1' * 51, '１' * 50, 'a' * 50, '1' * 50 + '\n']:
            self.assertFalse(guard.is_valid_secret(value))


    def test_install_idempotence_and_backups(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            home = Path(directory)
            install = installer_scope['install']
            self.assertEqual(len(install(home, 'all')), 3)
            self.assertEqual(install(home, 'all'), [])
            target = home / '.local/bin/chrome-guard'
            target.write_text('custom command')
            wrapper = home / '.local/bin/defaults'
            wrapper_before = wrapper.read_bytes()
            with self.assertRaises(RuntimeError):
                install(home, 'all')
            self.assertEqual(wrapper.read_bytes(), wrapper_before)
            self.assertEqual(target.read_text(), 'custom command')
            install(home, 'all', True)
            backups = list((home / '.local/share/browser-incognito-guard/backups').glob('*/chrome-guard'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), 'custom command')
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)

    def test_install_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / '.local/bin').mkdir(parents=True)
            victim = home / 'victim'
            victim.write_text('keep me')
            (home / '.local/bin/defaults').symlink_to(victim)
            with self.assertRaises(RuntimeError):
                installer_scope['install'](home, 'chrome', True)
            self.assertEqual(victim.read_text(), 'keep me')
            self.assertFalse((home / '.local/bin/chrome-guard').exists())

    def test_session_relocks_when_open_fails(self):
        with patch.object(guard, 'verify_gate', return_value=0), patch.object(guard, 'APP_PATH', ROOT), patch.object(guard, 'app_running', return_value=False), patch.object(guard, 'set_policy') as policy, patch.object(guard, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'simulated open failure')):
            self.assertEqual(guard.unlock_session(), 1)
            self.assertEqual([c.args[0] for c in policy.call_args_list], [0, 1])

    def test_interrupt_never_allows_wrapper_to_continue(self):
        with patch.object(guard.sys, 'argv', ['chrome-guard', 'gate']), patch.object(guard, 'verify_gate', side_effect=KeyboardInterrupt), patch.object(guard, 'lock', return_value=0) as lock:
            self.assertEqual(guard.main(), 130)
            lock.assert_called_once()


    def test_normal_lock_exit_status(self):
        for status in (0, 1):
            with patch.object(guard.sys, 'argv', ['chrome-guard', 'lock']), patch.object(guard, 'lock', return_value=status):
                self.assertEqual(guard.main(), status)

    def test_failed_cooldown_write_still_locks(self):
        with patch.object(guard, 'read_expected_digest', return_value='a' * 64), patch.object(guard, 'cooldown_remaining', return_value=0), patch.object(guard, 'read_hash_tui', return_value=False), patch.object(guard, 'set_lock_until', side_effect=RuntimeError('Keychain error')), patch.object(guard, 'set_policy') as policy, patch.object(guard, 'app_running', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'Keychain error'):
                guard.verify_gate()
            policy.assert_called_once_with(1)

    def test_selected_browser_and_existing_routes(self):
        for selected, expected in [('chrome', {'com.google.Chrome'}), ('ego', {'com.citrolabs.ego.lite'})]:
            data = installer_scope['payloads'](selected)
            scope = {'__name__': 'wrapper', '__file__': str(ROOT / 'defaults')}
            exec(compile(data['defaults'], 'defaults', 'exec'), scope)
            self.assertEqual(set(scope['GUARDS']), expected)
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            home = Path(directory)
            installer_scope['install'](home, 'ego')
            installer_scope['install'](home, 'chrome')
            scope = {'__name__': 'wrapper', '__file__': str(home / '.local/bin/defaults')}
            exec(compile((home / '.local/bin/defaults').read_bytes(), 'defaults', 'exec'), scope)
            self.assertEqual(set(scope['GUARDS']), set(wrapper.GUARDS))

if __name__ == '__main__':
    unittest.main()
