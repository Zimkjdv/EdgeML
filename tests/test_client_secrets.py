from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from examples import piapifd_edge_prediction as client
from examples import piapifd_prediction_config as config


class ClientSecretsTests(unittest.TestCase):
    def setUp(self):
        self.environ = patch.dict(os.environ, {}, clear=True)
        self.environ.start()
        self.addCleanup(self.environ.stop)

    def load_text(self, text):
        with patch.object(Path, 'open', return_value=StringIO(text)) as opener:
            result = config.load_client_secrets(Path('client.env'), required=True)
        opener.assert_called_once_with(encoding='utf-8-sig')
        return result

    def invoke(self, secrets, argv=(), prompts=()):
        pymysql = SimpleNamespace(connect=Mock(), cursors=SimpleNamespace(DictCursor=object()), MySQLError=RuntimeError)
        output, errors = StringIO(), StringIO()
        with patch.dict('sys.modules', {'pymysql': pymysql}), \
             patch.object(client, 'load_client_secrets', return_value=secrets) as loader, \
             patch.object(client.getpass, 'getpass', side_effect=prompts) as prompt, \
             patch.object(client, 'EdgeClient') as edge, patch.object(client, 'run', return_value={}), \
             redirect_stdout(output), redirect_stderr(errors):
            status = client.main(list(argv))
        self.assertEqual(status, 0, errors.getvalue())
        self.assertNotIn(secrets.api_token or 'FILE_TOKEN_EXAMPLE', output.getvalue() + errors.getvalue())
        self.assertNotIn(secrets.db_password or 'FILE_PASSWORD_EXAMPLE', output.getvalue() + errors.getvalue())
        return pymysql, edge, loader, prompt

    def test_reads_quotes_unicode_hash_and_literal_dollar_without_environment_mutation(self):
        os.environ['SHOULD_NOT_EXPAND'] = 'unexpected'
        secrets = self.load_text("# comment\nexport EDGEML_CLIENT_API_TOKEN='FILE_TOKEN_EXAMPLE'\n"
                                 'DB_PASSWORD="密碼 # ${SHOULD_NOT_EXPAND} % !"\n')
        self.assertEqual(secrets.api_token, 'FILE_TOKEN_EXAMPLE')
        self.assertEqual(secrets.db_password, '密碼 # ${SHOULD_NOT_EXPAND} % !')
        self.assertNotIn('EDGEML_CLIENT_API_TOKEN', os.environ)
        self.assertNotIn('DB_PASSWORD', os.environ)
        self.assertNotIn('FILE_TOKEN_EXAMPLE', repr(secrets))
        self.assertNotIn(secrets.db_password, repr(secrets))

    def test_empty_values_allow_prompt_fallback(self):
        secrets = self.load_text('EDGEML_CLIENT_API_TOKEN=\nDB_PASSWORD=\n')
        self.assertIsNone(secrets.api_token)
        self.assertIsNone(secrets.db_password)
        _, edge, _, prompt = self.invoke(secrets, prompts=['PROMPT_TOKEN_EXAMPLE', 'PROMPT_PASSWORD_EXAMPLE'])
        self.assertEqual(prompt.call_count, 2)
        self.assertEqual(edge.call_args.args[1], 'PROMPT_TOKEN_EXAMPLE')

    def test_missing_default_file_is_optional_but_explicit_file_is_required(self):
        with patch.object(Path, 'open', side_effect=FileNotFoundError()):
            secrets = config.load_client_secrets(Path('missing.env'))
            self.assertIsNone(secrets.api_token)
            with self.assertRaises(config.ConfigurationError):
                config.load_client_secrets(Path('missing.env'), required=True)

    def test_read_permission_and_encoding_errors_are_redacted(self):
        for failure in (PermissionError('SENSITIVE_EXAMPLE'), UnicodeError('SENSITIVE_EXAMPLE')):
            if isinstance(failure, OSError):
                patched = patch.object(Path, 'open', side_effect=failure)
            else:
                stream = Mock()
                stream.__enter__ = Mock(return_value=stream)
                stream.__exit__ = Mock(return_value=False)
                stream.read.side_effect = failure
                patched = patch.object(Path, 'open', return_value=stream)
            with patched, self.assertRaises(config.ConfigurationError) as error:
                config.load_client_secrets(Path('bad.env'))
            self.assertNotIn('SENSITIVE_EXAMPLE', str(error.exception))

    def test_malformed_duplicate_unknown_and_multiline_token_fail_without_echoing_secrets(self):
        cases = (
            "EDGEML_CLIENT_API_TOKEN='SECRET_EXAMPLE\n",
            'EDGEML_CLIENT_API_TOKEN=SECRET_EXAMPLE\nEDGEML_CLIENT_API_TOKEN=second\n',
            'EDGEML_API_TOKEN=SECRET_EXAMPLE\n',
            'DB_HOST=SECRET_EXAMPLE\n',
            "EDGEML_CLIENT_API_TOKEN='SECRET_EXAMPLE\ninjected'\n",
        )
        for text in cases:
            with self.subTest(text=text), self.assertRaises(config.ConfigurationError) as error:
                self.load_text(text)
            self.assertNotIn('SECRET_EXAMPLE', str(error.exception))

    def test_file_credentials_skip_both_prompts(self):
        secrets = config.ClientSecrets('FILE_TOKEN_EXAMPLE', 'FILE_PASSWORD_EXAMPLE')
        pymysql, edge, loader, prompt = self.invoke(secrets)
        loader.assert_called_once_with(config.DEFAULT_ENV_FILE, required=False)
        prompt.assert_not_called()
        self.assertEqual(edge.call_args.args[1], 'FILE_TOKEN_EXAMPLE')
        self.assertEqual(pymysql.connect.call_args.kwargs['password'], 'FILE_PASSWORD_EXAMPLE')

    def test_main_parses_default_file_without_real_api_or_db_access(self):
        original_open = Path.open
        opened = []

        def open_file(path, *args, **kwargs):
            if path == config.DEFAULT_ENV_FILE:
                opened.append(path)
                return StringIO('EDGEML_CLIENT_API_TOKEN=FILE_TOKEN_EXAMPLE\nDB_PASSWORD="FILE # PASSWORD_EXAMPLE"\n')
            return original_open(path, *args, **kwargs)

        pymysql = SimpleNamespace(connect=Mock(), cursors=SimpleNamespace(DictCursor=object()), MySQLError=RuntimeError)
        output = StringIO()
        with patch.object(Path, 'open', open_file), patch.dict('sys.modules', {'pymysql': pymysql}), \
             patch.object(client.getpass, 'getpass') as prompt, patch.object(client, 'EdgeClient') as edge, \
             patch.object(client, 'run', return_value={}), redirect_stdout(output):
            self.assertEqual(client.main([]), 0)
        self.assertEqual(opened, [config.DEFAULT_ENV_FILE])
        self.assertTrue(config.DEFAULT_ENV_FILE.is_absolute())
        self.assertEqual(config.DEFAULT_ENV_FILE.parent, Path(client.__file__).parent)
        prompt.assert_not_called()
        self.assertEqual(edge.call_args.args[1], 'FILE_TOKEN_EXAMPLE')
        self.assertEqual(pymysql.connect.call_args.kwargs['password'], 'FILE # PASSWORD_EXAMPLE')
        self.assertNotIn('FILE_TOKEN_EXAMPLE', output.getvalue())
        self.assertNotIn('FILE # PASSWORD_EXAMPLE', output.getvalue())

    def test_environment_overrides_file_without_mutating_it(self):
        os.environ.update(EDGEML_CLIENT_API_TOKEN='ENV_TOKEN_EXAMPLE', DB_PASSWORD='ENV_PASSWORD_EXAMPLE')
        secrets = config.ClientSecrets('FILE_TOKEN_EXAMPLE', 'FILE_PASSWORD_EXAMPLE')
        pymysql, edge, _, prompt = self.invoke(secrets)
        prompt.assert_not_called()
        self.assertEqual(edge.call_args.args[1], 'ENV_TOKEN_EXAMPLE')
        self.assertEqual(pymysql.connect.call_args.kwargs['password'], 'ENV_PASSWORD_EXAMPLE')
        self.assertEqual(secrets.api_token, 'FILE_TOKEN_EXAMPLE')

    def test_partial_file_only_prompts_for_missing_credential(self):
        pymysql, _, _, prompt = self.invoke(config.ClientSecrets('FILE_TOKEN_EXAMPLE'), prompts=['PROMPT_PASSWORD_EXAMPLE'])
        prompt.assert_called_once_with('MySQL password: ')
        self.assertEqual(pymysql.connect.call_args.kwargs['password'], 'PROMPT_PASSWORD_EXAMPLE')

    def test_explicit_file_and_time_entry_share_the_same_loading(self):
        start, end = '2026-10-06T00:00:00', '2026-10-07T00:00:00'
        args = client.parse_args(['--env-file', 'private/client.env', '--timestamp-from', start,
                                  '--timestamp-to', end], require_time_range=True)
        self.assertEqual(args.env_file, Path('private/client.env'))
        _, _, loader, _ = self.invoke(config.ClientSecrets('FILE_TOKEN_EXAMPLE', 'FILE_PASSWORD_EXAMPLE'),
                                      ['--env-file', 'private/client.env'])
        loader.assert_called_once_with(Path('private/client.env'), required=True)

    def test_loader_error_stops_before_prompt_or_connection_and_hides_secrets(self):
        pymysql = SimpleNamespace(connect=Mock(), MySQLError=RuntimeError)
        errors = StringIO()
        with patch.dict('sys.modules', {'pymysql': pymysql}), \
             patch.object(client, 'load_client_secrets', side_effect=config.ConfigurationError('Invalid client env syntax.')), \
             patch.object(client.getpass, 'getpass') as prompt, redirect_stderr(errors):
            self.assertEqual(client.main([]), 1)
        prompt.assert_not_called()
        pymysql.connect.assert_not_called()
        self.assertNotIn('Traceback', errors.getvalue())

    def test_help_and_invalid_cli_do_not_read_any_credential_file(self):
        for argv, code in ((['--help'], 0), (['--batch-size', '0'], 2)):
            with patch.object(client, 'load_client_secrets') as loader, \
                 patch.object(client.getpass, 'getpass') as prompt, \
                 redirect_stdout(StringIO()), redirect_stderr(StringIO()), self.assertRaises(SystemExit) as result:
                client.main(argv)
            self.assertEqual(result.exception.code, code)
            loader.assert_not_called()
            prompt.assert_not_called()


if __name__ == '__main__':
    unittest.main()
