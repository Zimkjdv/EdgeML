import argparse
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from examples import piapifd_edge_prediction as client


MODEL = {'id': client.DEFAULT_MODEL_ID, 'problem_type': 'regression', 'prediction_column': 'prediction',
         'features': [{'name': '紙種', 'dtype': 'object'}, {'name': '車速', 'dtype': 'float64'}]}
SNAPSHOT = {'車速': {'minimum': 410, 'maximum': 950}, '紙種': {'choices': ['甲']}}
MAPPINGS = [{'name_zh': '紙種', 'column_name': 'p_type'}, {'name_zh': '車速', 'column_name': 'speed'}]
COLUMNS = [{'Field': 'timestamp', 'Type': 'datetime', 'Null': 'NO', 'Extra': ''},
           {'Field': 'p_type', 'Type': 'varchar(50)', 'Null': 'YES', 'Extra': ''},
           {'Field': 'speed', 'Type': 'double', 'Null': 'YES', 'Extra': ''}]


def row(speed=730, paper='甲', second=0):
    return {'timestamp': datetime(2026, 10, 6, 0, 0, second), 'p_type': paper, 'speed': speed}


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.rules = client.feature_rules(MODEL, SNAPSHOT, MAPPINGS, COLUMNS)

    def test_chinese_mapping_minmax_inclusive_decimal_and_missing_actual_not_required(self):
        rows = [row(Decimal('410')), row(950, second=1)]
        accepted, data, rejected = client.prepare_batch(rows, self.rules)
        self.assertEqual(accepted, rows)
        self.assertEqual(data[0]['車速'], 410.)
        self.assertEqual(data[0]['紙種'], '甲')
        self.assertNotIn('實際值', data[0])
        self.assertEqual(rejected, {})

    def test_missing_invalid_nonfinite_and_out_of_training_range_are_excluded(self):
        rows = [row(None), row(730, ' '), row('bad'), row(float('nan')), row(float('inf')),
                row(3.402823e38), row(409.9), row(950.1), row(730, second=1)]
        accepted, data, rejected = client.prepare_batch(rows, self.rules)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(data), 1)
        self.assertEqual(rejected, {'missing': 2, 'invalid_numeric': 3, 'outside_training_range': 3})

    def test_constant_training_feature_and_fractional_integer(self):
        model = deepcopy(MODEL); model['features'][1]['dtype'] = 'int64'
        rules = client.feature_rules(model, {'車速': {'minimum': 730, 'maximum': 730}}, MAPPINGS, COLUMNS)
        accepted, data, rejected = client.prepare_batch([row(730), row(730.5)], rules)
        self.assertEqual(len(accepted), 1)
        self.assertIsInstance(data[0]['車速'], int)
        self.assertEqual(rejected['invalid_numeric'], 1)

    def test_missing_then_invalid_then_range_statistics_do_not_depend_on_feature_order(self):
        rules = self.rules + [client.FeatureRule('基重', 'basis_weight', 'float64', Decimal('100'), Decimal('340'))]
        rows = [{**row(409), 'basis_weight': None}, {**row(409, second=1), 'basis_weight': 'bad'},
                {**row(409, second=2), 'basis_weight': 200}, {**row(730, second=3), 'basis_weight': 200}]
        accepted, _, rejected = client.prepare_batch(rows, rules)
        self.assertEqual(accepted, [rows[3]])
        self.assertEqual(rejected, {'missing': 1, 'invalid_numeric': 1, 'outside_training_range': 1})
        _, _, reversed_rejected = client.prepare_batch(rows, list(reversed(rules)))
        self.assertEqual(rejected, reversed_rejected)

    def test_mapping_missing_or_ambiguous_fails(self):
        for mappings in ([], MAPPINGS + [MAPPINGS[0]]):
            with self.assertRaises(client.IntegrationError):
                client.feature_rules(MODEL, SNAPSHOT, mappings, COLUMNS)

    def test_explicit_alias_resolves_db_name_but_keeps_model_payload_name(self):
        mappings = [{**item, 'name_zh': '速度'} if item['column_name'] == 'speed' else item for item in MAPPINGS]
        rules = client.feature_rules(MODEL, SNAPSHOT, mappings, COLUMNS, {'車速': '速度'})
        _, payload, _ = client.prepare_batch([row()], rules)
        self.assertEqual(payload[0]['車速'], 730.)
        self.assertNotIn('速度', payload[0])
        self.assertEqual(mappings[1]['name_zh'], '速度')

    def test_exact_name_takes_priority_and_alias_collisions_are_rejected(self):
        rules = client.feature_rules(MODEL, SNAPSHOT, MAPPINGS, COLUMNS, {'車速': '不存在'})
        self.assertEqual(rules[1].column, 'speed')
        model = deepcopy(MODEL)
        model['features'].append({'name': '速度', 'dtype': 'float64'})
        with self.assertRaises(client.IntegrationError):
            client.feature_rules(model, {**SNAPSHOT, '速度': SNAPSHOT['車速']}, MAPPINGS, COLUMNS, {'速度': '車速'})

    def test_alias_file_validation_and_default_configuration(self):
        aliases = client.load_feature_aliases(client.parse_args([]).feature_aliases)
        self.assertEqual(aliases['前段水份'], '前段水分')
        self.assertEqual(aliases['濃乾 (面)'], '濃乾(面)')
        for invalid in ('[]', '{"x": null}', '{"x": " "}', '{"x": "a", "x": "b"}', 'bad'):
            with patch.object(Path, 'read_text', return_value=invalid), self.assertRaises(client.IntegrationError):
                client.load_feature_aliases(Path('aliases.json'))

    def test_missing_invalid_training_ranges_fail_closed(self):
        for bounds in ({}, {'minimum': None, 'maximum': 1000}, {'minimum': 950, 'maximum': 410},
                       {'minimum': 0, 'maximum': float('inf')}):
            with self.assertRaises(client.IntegrationError):
                client.feature_rules(MODEL, {'車速': bounds}, MAPPINGS, COLUMNS)

    def test_model_metadata_uses_existing_api_and_requires_snapshot(self):
        edge = client.EdgeClient('http://127.0.0.1:8010/api', 'test-token')
        edge.request = Mock(side_effect=[[MODEL], {'origin': 'training_snapshot', 'features': SNAPSHOT}])
        self.assertEqual(edge.model_and_ranges(MODEL['id']), (MODEL, SNAPSHOT))
        self.assertIn('?source=registry', edge.request.call_args_list[1].args[0])
        edge.request = Mock(side_effect=[[MODEL], {'origin': 'source_dataset', 'features': SNAPSHOT}])
        with self.assertRaises(client.IntegrationError): edge.model_and_ranges(MODEL['id'])

    def test_prediction_identity_count_drop_and_finite_checks(self):
        _, data, _ = client.prepare_batch([row(), row(second=1)], self.rules)
        result = {'model_id': MODEL['id'], 'prediction_column': 'prediction', 'dropped_rows': 0,
                  'out_of_range_rows': 0,
                  'records': [{**item, 'prediction': 7.1234} for item in data]}
        self.assertEqual(client.checked_predictions(result, MODEL, data), [7.1234, 7.1234])
        for change in ('model', 'order', 'count', 'drop', 'nan', 'bool', 'structure', 'old_api', 'range_drop'):
            invalid = deepcopy(result)
            if change == 'model': invalid['model_id'] = 'another'
            if change == 'order': invalid['records'].reverse()
            if change == 'count': invalid['records'].pop()
            if change == 'drop': invalid['dropped_rows'] = 1
            if change == 'nan': invalid['records'][0]['prediction'] = float('nan')
            if change == 'bool': invalid['records'][0]['prediction'] = True
            if change == 'structure': invalid['records'] = [1, 2]
            if change == 'old_api': invalid.pop('out_of_range_rows')
            if change == 'range_drop': invalid['out_of_range_rows'] = 1
            with self.subTest(change=change), self.assertRaises(client.IntegrationError):
                client.checked_predictions(invalid, MODEL, data)

    def test_schema_copies_source_audit_timestamps_and_guards_generated_columns(self):
        columns = COLUMNS + [{'Field': 'created_at', 'Type': 'datetime(6)', 'Null': 'NO', 'Extra': 'DEFAULT_GENERATED'},
                            {'Field': 'updated_at', 'Type': 'datetime(6)', 'Null': 'NO', 'Extra': 'DEFAULT_GENERATED on update CURRENT_TIMESTAMP(6)'}]
        definition = client.schema_definition(columns)
        sql = client.create_target_sql('piapifd_edge', 'pidata1_predict', definition)
        self.assertIn('PRIMARY KEY (`timestamp`, `model_id`)', sql)
        self.assertIn('`actual_value` double NULL', sql)
        self.assertNotIn('ON UPDATE', sql.upper())
        columns[1] = {**columns[1], 'Extra': 'VIRTUAL GENERATED'}
        with self.assertRaises(client.IntegrationError): client.schema_definition(columns)

    def test_identifiers_and_bound_values_are_not_interpolated(self):
        args = client.parse_args(['--mode', 'write', '--timestamp-from', '2026-10-06T00:00:00'])
        sql, values = client.source_query(args, None, 200)
        self.assertIn('`piapi_fd`.`pidata1_merged`', sql)
        self.assertIn('`piapifd_edge`.`pidata1_predict`', sql)
        self.assertNotIn(MODEL['id'], sql)
        self.assertIn(MODEL['id'], values)
        self.assertNotIn('2026-10-06', sql)
        for bad in ('table;DROP TABLE x', 'x.y', '`anything`'):
            with self.assertRaises(client.IntegrationError): client.quoted(bad)

    def test_write_inserts_null_actual_and_never_overwrites_measured_actual(self):
        connection, cursor = Mock(), Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor.rowcount = 1
        args = client.parse_args(['--mode', 'write'])
        rows = [row()]
        self.assertEqual(client.write_batch(connection, args, COLUMNS, rows, [7.]), 1)
        sql, values = cursor.executemany.call_args.args
        self.assertEqual(values[0][len(COLUMNS)], None)
        self.assertEqual(values[0][len(COLUMNS) + 1], 7.)
        self.assertEqual(sql.split('ON DUPLICATE KEY UPDATE')[1].strip(), '`model_id`=`model_id`')
        connection.commit.assert_called_once()
        connection.rollback.assert_not_called()

    def test_write_failure_rolls_back_only_current_batch(self):
        connection, cursor = Mock(), Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor.executemany.side_effect = RuntimeError('test write error')
        with self.assertRaises(RuntimeError):
            client.write_batch(connection, client.parse_args(['--mode', 'write']), COLUMNS, [row()], [7.])
        connection.rollback.assert_called_once()
        connection.commit.assert_not_called()

    def test_default_preview_does_not_call_prediction_or_initialize_target(self):
        args = client.parse_args([])
        self.assertEqual(args.mode, 'preview')
        self.assertEqual(args.source_table, 'pidata1_merged')
        self.assertEqual(args.target_table, 'pidata1_predict')
        self.assertIsNone(args.limit)
        connection, cursor = Mock(), Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor.fetchall.side_effect = [COLUMNS, MAPPINGS, [{'COLUMN_NAME': 'timestamp'}], [row()], []]
        cursor.fetchone.return_value = {'upper_bound': row()['timestamp']}
        edge = Mock(); edge.model_and_ranges.return_value = (MODEL, SNAPSHOT)
        with redirect_stdout(StringIO()): totals = client.run(connection, edge, args)
        self.assertEqual(totals['eligible'], 1)
        edge.request.assert_not_called()
        self.assertTrue(all(call.args[0].startswith(('SELECT', 'SHOW')) for call in cursor.execute.call_args_list))
        connection.begin.assert_not_called()

    def test_cli_limits_init_mode_and_timezone_validation(self):
        for argv in (['--init-target'], ['--limit', '0'], ['--batch-size', '10001'], ['--target-db', 'piapi_fd']):
            with self.subTest(argv=argv), redirect_stderr(StringIO()), self.assertRaises(SystemExit): client.parse_args(argv)
        with self.assertRaises(argparse.ArgumentTypeError): client.parse_time('2026-10-06T00:00:00+08:00')

    def test_default_visits_more_than_1000_rows_in_bounded_batches(self):
        connection, cursor = Mock(), Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        rows = [{**row(), 'timestamp': row()['timestamp'] + timedelta(seconds=i)} for i in range(1205)]
        batches = [rows[i:i + 200] for i in range(0, len(rows), 200)]
        cursor.fetchall.side_effect = [COLUMNS, MAPPINGS, [{'COLUMN_NAME': 'timestamp'}], *batches, []]
        cursor.fetchone.return_value = {'upper_bound': rows[-1]['timestamp']}
        edge = Mock(); edge.model_and_ranges.return_value = (MODEL, SNAPSHOT)
        with redirect_stdout(StringIO()): totals = client.run(connection, edge, client.parse_args([]))
        self.assertEqual(totals['read'], 1205)
        self.assertEqual(totals['eligible'], 1205)
        paging = [call.args for call in cursor.execute.call_args_list if call.args[0].startswith('SELECT s.*')]
        self.assertEqual(len(paging), 8)
        self.assertTrue(all('s.`timestamp` <= %s' in sql and values[-1] == 200 for sql, values in paging))
        self.assertTrue(all(rows[-1]['timestamp'] in values for _, values in paging))
        self.assertIn(rows[199]['timestamp'], paging[1][1])

    def test_explicit_limit_only_caps_rows_when_requested(self):
        connection, cursor = Mock(), Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        rows = [{**row(), 'timestamp': row()['timestamp'] + timedelta(seconds=i)} for i in range(350)]
        cursor.fetchall.side_effect = [COLUMNS, MAPPINGS, [{'COLUMN_NAME': 'timestamp'}], rows[:200], rows[200:]]
        cursor.fetchone.return_value = {'upper_bound': datetime(2026, 10, 7)}
        edge = Mock(); edge.model_and_ranges.return_value = (MODEL, SNAPSHOT)
        with redirect_stdout(StringIO()): totals = client.run(connection, edge, client.parse_args(['--limit', '350']))
        self.assertEqual(totals['read'], 350)
        paging = [call.args[1][-1] for call in cursor.execute.call_args_list if call.args[0].startswith('SELECT s.*')]
        self.assertEqual(paging, [200, 150])

    def test_time_entry_requires_both_bounds_and_query_is_half_open(self):
        start, end = '2026-10-06T00:00:00', '2026-10-07T00:00:00'
        for argv in ([], ['--timestamp-from', start], ['--timestamp-to', end],
                     ['--timestamp-from', end, '--timestamp-to', start]):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                client.parse_args(argv, require_time_range=True)
        args = client.parse_args(['--timestamp-from', start, '--timestamp-to', end], require_time_range=True)
        self.assertIsNone(args.limit)
        sql, values = client.source_query(args, None, 200, datetime(2026, 10, 8))
        self.assertIn('s.`timestamp` >= %s', sql)
        self.assertIn('s.`timestamp` < %s', sql)
        self.assertEqual(values, (datetime(2026, 10, 6), datetime(2026, 10, 7), datetime(2026, 10, 8), 200))

    def test_empty_source_finishes_without_prediction_or_paging(self):
        connection, cursor = Mock(), Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor.fetchall.side_effect = [COLUMNS, MAPPINGS, [{'COLUMN_NAME': 'timestamp'}]]
        cursor.fetchone.return_value = {'upper_bound': None}
        edge = Mock(); edge.model_and_ranges.return_value = (MODEL, SNAPSHOT)
        self.assertEqual(client.run(connection, edge, client.parse_args([]))['read'], 0)
        edge.request.assert_not_called()
        self.assertFalse(any(call.args[0].startswith('SELECT s.*') for call in cursor.execute.call_args_list))

    def test_target_initialization_is_explicit_and_only_creates_destination(self):
        connection, cursor = Mock(), Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor.fetchall.return_value = []
        with self.assertRaises(client.IntegrationError):
            client.ensure_target(connection, client.parse_args(['--mode', 'write']), COLUMNS)
        self.assertEqual(len(cursor.execute.call_args_list), 1)
        cursor.reset_mock()
        cursor.fetchall.side_effect = [[], [{'COLUMN_NAME': 'timestamp'}, {'COLUMN_NAME': 'model_id'}]]
        cursor.fetchone.return_value = {'ENGINE': 'InnoDB'}
        client.ensure_target(connection, client.parse_args(['--mode', 'write', '--init-target']), COLUMNS)
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        creates = [sql for sql in statements if sql.startswith('CREATE')]
        self.assertEqual(len(creates), 2)
        self.assertTrue(all('`piapifd_edge`' in sql for sql in creates))
        self.assertTrue(all('`piapi_fd`' not in sql for sql in creates))

    def test_existing_target_schema_mismatch_stops_without_alter_or_dml(self):
        connection, cursor = Mock(), Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        cursor.fetchall.return_value = [{'COLUMN_NAME': 'timestamp', 'COLUMN_TYPE': 'varchar(100)', 'IS_NULLABLE': 'NO'}]
        with self.assertRaises(client.IntegrationError):
            client.ensure_target(connection, client.parse_args(['--mode', 'write', '--init-target']), COLUMNS)
        self.assertTrue(all(call.args[0].startswith('SELECT') for call in cursor.execute.call_args_list))

    def test_full_write_flow_uses_existing_prediction_api_and_cross_database_insert(self):
        connection, cursor = Mock(), Mock()
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        definition = client.schema_definition(COLUMNS)
        existing = [{'COLUMN_NAME': name, 'COLUMN_TYPE': kind, 'IS_NULLABLE': 'YES' if nullable else 'NO'}
                    for name, kind, nullable in definition]
        cursor.fetchall.side_effect = [COLUMNS, MAPPINGS, [{'COLUMN_NAME': 'timestamp'}], existing,
                                      [{'COLUMN_NAME': 'timestamp'}, {'COLUMN_NAME': 'model_id'}], [row()], []]
        cursor.fetchone.side_effect = [{'upper_bound': row()['timestamp']}, {'ENGINE': 'InnoDB'}]
        cursor.rowcount = 1
        edge = Mock(); edge.model_and_ranges.return_value = (MODEL, SNAPSHOT)
        _, data, _ = client.prepare_batch([row()], self.rules)
        edge.request.return_value = {'model_id': MODEL['id'], 'prediction_column': 'prediction', 'dropped_rows': 0,
                                     'out_of_range_rows': 0,
                                     'records': [{**data[0], 'prediction': 7.1234}]}
        with redirect_stdout(StringIO()):
            totals = client.run(connection, edge, client.parse_args(['--mode', 'write']))
        self.assertEqual(totals['inserted'], 1)
        path, payload = edge.request.call_args.args
        self.assertEqual(path, '/predict/json')
        self.assertEqual(payload['model_id'], MODEL['id'])
        self.assertEqual(payload['ground_truth_column'], '')
        self.assertEqual(payload['training_range_policy'], 'drop')
        self.assertEqual(payload['data'][0]['車速'], 730.)
        self.assertIn('INSERT INTO `piapifd_edge`.`pidata1_predict`', cursor.executemany.call_args.args[0])
        connection.commit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
