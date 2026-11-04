"""Offline-only tests for trusted-terminal credential input. No networking."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import avito_terminal_connect as app
import avito_preflight as core


class TerminalConnectTests(unittest.TestCase):
    def test_default_offline_no_prompts(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = app.main([], input_fn=lambda *a: self.fail('should not prompt'),
                          secret_fn=lambda *a: self.fail('should not get secret'))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())['network'], False)

    def test_live_non_tty_rejected(self):
        fake = Mock(isatty=lambda: False)
        with contextlib.redirect_stderr(io.StringIO()):
            rc = app.main(['--live'], stdin=fake,
                          input_fn=lambda *a: self.fail('should not prompt'))
        self.assertEqual(rc, 2)

    def test_live_cancel_no_secret(self):
        fake = Mock(isatty=lambda: True)
        with contextlib.redirect_stdout(io.StringIO()):
            rc = app.main(['--live'], stdin=fake, input_fn=lambda _: 'NO',
                          secret_fn=lambda _: self.fail('should not prompt'))
        self.assertEqual(rc, 2)

    def test_live_success_hidden_input_and_sanitized_output(self):
        fake = Mock(isatty=lambda: True)
        prompts=[]
        secrets=iter(['CLIENT_ID_SECRET_TEST', 'CLIENT_SECRET_SECRET_TEST'])
        def hidden(prompt):
            prompts.append(prompt)
            return next(secrets)
        def diagnostic(a,b):
            self.assertEqual(a, 'CLIENT_ID_SECRET_TEST')
            self.assertEqual(b, 'CLIENT_SECRET_SECRET_TEST')
            return [core.Result('token',True,200,'authorized'),
                    core.Result('profile',True,200,'read_only_ok')]
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc=app.main(['--live'],stdin=fake,input_fn=lambda _: 'YES',
                        secret_fn=hidden,run_fn=diagnostic)
        self.assertEqual(rc,0)
        self.assertEqual(len(prompts),2)
        self.assertNotIn('CLIENT_ID_SECRET_TEST',out.getvalue())
        self.assertNotIn('CLIENT_SECRET_SECRET_TEST',out.getvalue())

    def test_error_not_logged(self):
        fake = Mock(isatty=lambda: True)
        it=iter(['secret_one','secret_two'])
        with contextlib.redirect_stdout(io.StringIO()) as out,contextlib.redirect_stderr(io.StringIO()) as err:
            rc = app.main(['--live'], stdin=fake,input_fn=lambda _: 'YES',
              secret_fn=lambda _: next(it),
              run_fn=lambda *a: (_ for _ in ()).throw(ValueError('secret_two')))
        self.assertEqual(rc,2)
        self.assertNotIn('secret_two',out.getvalue()+err.getvalue())

    def test_auth_rejected_no_profile_and_redacted(self):
        fake=Mock(isatty=lambda:True)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc=app.main(['--live'],stdin=fake,input_fn=lambda _: 'YES',
              secret_fn=lambda _: 'value',
              run_fn=lambda *a:[core.Result('token',False,400,'unauthorized_client')])
        self.assertEqual(rc,1)
        self.assertIn('unauthorized_client',out.getvalue())

if __name__=='__main__':
    unittest.main()