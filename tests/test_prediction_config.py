from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from examples import piapifd_edge_prediction as client
from examples import piapifd_prediction_config as config


class PredictionConfigTests(unittest.TestCase):
    def setUp(self):
        self.environ = patch.dict(os.environ, {}, clear=True)
        self.environ.start()
        self.addCleanup(self.environ.stop)

    def parse_ini(self, content, argv=(), **kwargs):
        with patch.object(Path, 'open', return_value=StringIO(content)):
            return client.parse_args(['--config', str(config.DEFAULT_CONFIG), *argv], **kwargs)

    def test_shipped_settings_keep_safe_preview_and_all_rows(self):
        args = client.parse_args([])
        self.assertEqual(args.api_url, 'http://127.0.0.1:8010/api')
        self.assertEqual(args.model_id, client.DEFAULT_MODEL_ID)
        self.assertEqual(args.batch_size, 200)
        self.assertIsNone(args.limit)
        self.assertEqual(args.mode, 'preview')
        self.assertFalse(args.init_target)
        self.assertEqual(args.mapping_table, 'pidata1_mapping')
        self.assertEqual(args.feature_aliases, config.DEFAULT_CONFIG.resolve().with_name('piapifd_feature_aliases.json'))

    def test_config_overrides_builtins_and_parses_types_without_interpolation(self):
        args = self.parse_ini('''[api]
url = http://localhost:8000/api
model_id = 工廠-model
timeout = 12.5
[mysql]
host = db.internal
port = 3307
user = svc%prediction
connect_timeout = 7
read_timeout = 8
write_timeout = 9
[source]
database = source_db
table = sensor_rows
mapping_table = sensor_mapping
[target]
database = target_db
table = predictions
[prediction]
batch_size = 50
limit = 400
feature_aliases = mappings/aliases.json
''')
        self.assertEqual(args.api_url, 'http://localhost:8000/api')
        self.assertEqual(args.model_id, '工廠-model')
        self.assertEqual(args.api_timeout, 12.5)
        self.assertEqual((args.host, args.port, args.user), ('db.internal', 3307, 'svc%prediction'))
        self.assertEqual((args.db_connect_timeout, args.db_read_timeout, args.db_write_timeout), (7, 8, 9))
        self.assertEqual((args.source_db, args.source_table, args.mapping_table), ('source_db', 'sensor_rows', 'sensor_mapping'))
        self.assertEqual((args.target_db, args.target_table), ('target_db', 'predictions'))
        self.assertEqual((args.batch_size, args.limit), (50, 400))
        self.assertEqual(args.feature_aliases, config.DEFAULT_CONFIG.resolve().parent / 'mappings/aliases.json')

    def test_cli_then_existing_environment_then_ini_precedence(self):
        content = '[api]\nurl=http://ini:8010/api\nmodel_id=ini-model\n[mysql]\nport=3307\n[prediction]\nbatch_size=50\n'
        os.environ.update(EDGEML_CLIENT_API_URL='http://env:8010/api', EDGEML_MODEL_ID='env-model', DB_PORT='3308')
        args = self.parse_ini(content)
        self.assertEqual((args.api_url, args.model_id, args.port, args.batch_size), ('http://env:8010/api', 'env-model', 3308, 50))
        args = self.parse_ini(content, ['--api-url', 'http://cli:8000/api', '--model-id', 'cli-model', '--port', '3309', '--batch-size', '60'])
        self.assertEqual((args.api_url, args.model_id, args.port, args.batch_size), ('http://cli:8000/api', 'cli-model', 3309, 60))

    def test_cli_alias_path_is_not_rebased_to_config_directory(self):
        args = self.parse_ini('[prediction]\nfeature_aliases=ini.json', ['--feature-aliases', 'cli.json'])
        self.assertEqual(args.feature_aliases, Path('cli.json'))

    def test_invalid_types_values_and_unknown_keys_fail_before_db_access(self):
        invalid = (
            '[mysql]\nport=no', '[mysql]\nport=0', '[prediction]\nbatch_size=0',
            '[prediction]\nlimit=-1', '[api]\ntimeout=nan', '[mysql]\nread_timeout=0',
            '[source]\ntable=a;DROP', '[source]\nmapping_table=x.y',
            '[api]\nurl=ftp://localhost/api', '[api]\nmodel_id=',
            '[prediction]\nmode=write', '[prediction]\ninit_target=true',
            '[other]\nx=y', '[DEFAULT]\nport=3306', '[api]\nurl=a\nurl=b',
        )
        for content in invalid:
            with self.subTest(content=content), redirect_stderr(StringIO()), self.assertRaises(SystemExit) as failure:
                self.parse_ini(content)
            self.assertEqual(failure.exception.code, 2)

    def test_credentials_in_ini_or_url_are_rejected_without_echoing_values(self):
        for content in ('[api]\ntoken=SECRET_EXAMPLE', '[mysql]\npassword=SECRET_EXAMPLE',
                        '[api]\nurl=http://user:SECRET_EXAMPLE@localhost:8000/api'):
            errors = StringIO()
            with redirect_stderr(errors), self.assertRaises(SystemExit):
                self.parse_ini(content)
            self.assertNotIn('SECRET_EXAMPLE', errors.getvalue())

    def test_missing_or_broken_config_fails_but_help_remains_available(self):
        for failure in (FileNotFoundError(), UnicodeError()):
            with patch.object(Path, 'open', side_effect=failure), redirect_stderr(StringIO()), self.assertRaises(SystemExit) as exit_info:
                client.parse_args(['--config', 'missing.ini'])
            self.assertEqual(exit_info.exception.code, 2)
        with patch.object(Path, 'open', side_effect=FileNotFoundError()) as opener, redirect_stdout(StringIO()), self.assertRaises(SystemExit) as exit_info:
            client.parse_args(['--config', 'missing.ini', '--help'])
        self.assertEqual(exit_info.exception.code, 0)
        opener.assert_not_called()

    def test_invalid_environment_port_reports_argument_error_not_traceback(self):
        os.environ['DB_PORT'] = 'invalid-port'
        errors = StringIO()
        with redirect_stderr(errors), self.assertRaises(SystemExit) as failure:
            client.parse_args([])
        self.assertEqual(failure.exception.code, 2)
        self.assertNotIn('Traceback', errors.getvalue())

    def test_time_entry_reuses_settings_but_still_requires_explicit_bounds(self):
        content = '[prediction]\nbatch_size=25\nlimit=\n'
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            self.parse_ini(content, require_time_range=True)
        args = self.parse_ini(content, ['--timestamp-from', '2026-10-06T00:00:00',
                                       '--timestamp-to', '2026-10-07T00:00:00'], require_time_range=True)
        self.assertEqual(args.batch_size, 25)
        self.assertIsNone(args.limit)
        self.assertEqual(args.mode, 'preview')

    def test_mapping_table_is_used_in_read_only_source_query(self):
        connection, cursor = Mock(), Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor.fetchall.side_effect = [[], [], [{'COLUMN_NAME': 'timestamp'}]]
        cursor.fetchone.return_value = {'upper_bound': None}
        edge = Mock()
        edge.model_and_ranges.return_value = ({}, {})
        with patch.object(client, 'feature_rules', return_value=[]):
            self.assertEqual(client.run(connection, edge, client.parse_args(['--mapping-table', 'sensor_mapping']))['read'], 0)
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertTrue(any('FROM `piapi_fd`.`sensor_mapping`' in sql for sql in statements))
        self.assertTrue(all(sql.startswith(('SELECT', 'SHOW')) for sql in statements))
        edge.request.assert_not_called()

    def test_runtime_uses_configured_timeouts_without_real_connections(self):
        pymysql = SimpleNamespace(connect=Mock(), cursors=SimpleNamespace(DictCursor=object()), MySQLError=RuntimeError)
        os.environ.update(EDGEML_CLIENT_API_TOKEN='test-token', DB_PASSWORD='test-password')
        with patch.dict('sys.modules', {'pymysql': pymysql}), patch.object(client, 'EdgeClient') as edge, \
             patch.object(client, 'load_client_secrets', return_value=config.ClientSecrets()), \
             patch.object(client, 'run', return_value={}), redirect_stdout(StringIO()):
            self.assertEqual(client.main(['--api-timeout', '13', '--db-connect-timeout', '7',
                                         '--db-read-timeout', '8', '--db-write-timeout', '9']), 0)
        self.assertEqual(edge.call_args.kwargs['timeout'], 13)
        kwargs = pymysql.connect.call_args.kwargs
        self.assertEqual((kwargs['connect_timeout'], kwargs['read_timeout'], kwargs['write_timeout']), (7, 8, 9))
        pymysql.connect.return_value.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
