"""MySQL -> existing EdgeML APIs -> MySQL. Preview is the read-only default.

Python 3.12; install examples/requirements-piapifd.txt for database access.
Credentials come from environment variables, client .env.local or masked prompts,
never this Python file or the shared INI.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import getpass
import json
import math
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

if __package__:
    from .piapifd_prediction_config import ConfigurationError, DEFAULT_CONFIG, DEFAULT_ENV_FILE, DEFAULT_MODEL_ID, PredictionSettings, load_client_secrets, load_settings
else:
    from piapifd_prediction_config import ConfigurationError, DEFAULT_CONFIG, DEFAULT_ENV_FILE, DEFAULT_MODEL_ID, PredictionSettings, load_client_secrets, load_settings

ROW_KEY = '_edgeml_source_timestamp'
EXTRA_COLUMNS = ('actual_value', 'prediction_value', 'model_id', 'predicted_at')
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,63}\Z')
MYSQL_TYPE = re.compile(r'(?:double|float|(?:tiny|small|medium|big)?int(?:\(\d+\))?(?: unsigned)?|'
                        r'decimal\(\d+,\d+\)|varchar\(\d+\)|(?:datetime|timestamp)(?:\([0-6]\))?)\Z')


class IntegrationError(ValueError):
    """A safe operator-facing failure without credential or row contents."""


def quoted(name: str) -> str:
    if not IDENTIFIER.fullmatch(name):
        raise IntegrationError('Database/table/column identifiers must be ASCII letters, numbers or underscores (max 64).')
    return f'`{name}`'


def table_path(database: str, table: str) -> str:
    return f'{quoted(database)}.{quoted(table)}'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward Authorization to a redirected host.


class EdgeClient:
    def __init__(self, api_url: str, token: str, timeout: float = 60):
        parsed = urlsplit(api_url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise IntegrationError('Provide an HTTP(S) API URL without credentials, query or fragment.')
        self.api_url, self.token, self.timeout = api_url.rstrip('/'), token, timeout
        self.opener = build_opener(NoRedirect())

    def request(self, path: str, payload: dict | None = None):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8') if payload is not None else None
        request = Request(self.api_url + path, data=body,
            headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'},
            method='POST' if payload is not None else 'GET')
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except HTTPError as exc:
            raise IntegrationError(f'EdgeML API returned HTTP {exc.code}; check token, active model and request limits.') from None
        except (URLError, TimeoutError, OSError, UnicodeError, ValueError):
            raise IntegrationError('EdgeML connection failed or returned invalid JSON; no batch results were written.') from None

    def model_and_ranges(self, model_id: str):
        models = self.request('/models')
        if not isinstance(models, list) or any(not isinstance(model, dict) for model in models):
            raise IntegrationError('EdgeML returned invalid model metadata.')
        matches = [model for model in models if model.get('id') == model_id]
        if len(matches) != 1 or matches[0].get('problem_type') != 'regression':
            raise IntegrationError('Model must be an active registered regression model.')
        snapshot = self.request(f'/optimization/models/{quote(model_id, safe="")}/defaults?source=registry')
        # A live source dataset is not necessarily the data used when this model was fitted.
        if not isinstance(snapshot, dict) or snapshot.get('origin') != 'training_snapshot' or not isinstance(snapshot.get('features'), dict):
            raise IntegrationError('Saved training ranges are unavailable; publish/retrain with a feature snapshot first.')
        return matches[0], snapshot.get('features', {})


@dataclass(frozen=True)
class FeatureRule:
    name: str
    column: str
    dtype: str
    minimum: Decimal | None = None
    maximum: Decimal | None = None

    @property
    def numeric(self):
        return self.dtype.lower().startswith(('float', 'int', 'uint'))


def load_feature_aliases(path: Path) -> dict[str, str]:
    def unique_keys(pairs):
        aliases = {}
        for key, value in pairs:
            if key in aliases:
                raise IntegrationError('Feature alias configuration contains duplicate keys.')
            aliases[key] = value
        return aliases

    try:
        aliases = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=unique_keys)
    except (OSError, UnicodeError, ValueError):
        raise IntegrationError('Cannot read a valid feature-alias JSON file; check --feature-aliases.') from None
    if not isinstance(aliases, dict) or any(
        not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip()
        for key, value in aliases.items()
    ):
        raise IntegrationError('Feature aliases must map nonempty model feature names to nonempty DB mapping names.')
    return aliases


def feature_rules(model: dict, snapshot: dict, mappings: list[dict], source_columns: list[dict],
                  aliases: dict[str, str] | None = None) -> list[FeatureRule]:
    available = {column['Field'] for column in source_columns}
    names = [feature['name'] for feature in model['features']]
    if not names or len(set(names)) != len(names) or ROW_KEY in names:
        raise IntegrationError('Model has empty/duplicate/reserved feature names.')
    rules = []
    for feature in model['features']:
        name, dtype = feature['name'], feature['dtype']
        matches = [mapping for mapping in mappings if mapping['name_zh'] == name]
        if not matches and aliases and name in aliases:
            matches = [mapping for mapping in mappings if mapping['name_zh'] == aliases[name]]
        if len(matches) != 1 or matches[0]['column_name'] not in available:
            raise IntegrationError(f'Missing or ambiguous pidata1_mapping/source column for feature: {name}')
        low = high = None
        if dtype.lower().startswith(('float', 'int', 'uint')):
            bounds = snapshot.get(name, {})
            try:
                low, high = Decimal(str(bounds['minimum'])), Decimal(str(bounds['maximum']))
                if not low.is_finite() or not high.is_finite() or low > high: raise ValueError
            except (KeyError, InvalidOperation, TypeError, ValueError):
                raise IntegrationError(f'Saved numeric training range is missing/invalid for: {name}') from None
        rules.append(FeatureRule(name, matches[0]['column_name'], dtype, low, high))
    if len({rule.column for rule in rules}) != len(rules):
        raise IntegrationError('Several model features map to the same database column.')
    return rules


def prepare_batch(rows: list[dict], rules: list[FeatureRule]):
    accepted, payload, rejected = [], [], Counter()
    for row in rows:
        if not isinstance(row.get('timestamp'), datetime):
            raise IntegrationError('Source timestamp must be a non-null MySQL DATETIME.')
        # Classify missing inputs first across the entire feature set, rather
        # than reporting an early range violation on a later-incomplete row.
        if any(row.get(rule.column) is None or isinstance(row.get(rule.column), str)
               and not row[rule.column].strip() for rule in rules):
            rejected['missing'] += 1
            continue
        record = {ROW_KEY: row['timestamp'].isoformat(timespec='microseconds')}
        reason = None
        outside_range = False
        for rule in rules:
            value = row.get(rule.column)
            if rule.numeric:
                try:
                    number = Decimal(str(value))
                    if isinstance(value, bool) or not number.is_finite(): raise ValueError
                    if rule.dtype.lower().startswith(('int', 'uint')) and number != number.to_integral_value(): raise ValueError
                    if not rule.minimum <= number <= rule.maximum:
                        outside_range = True
                    value = int(number) if rule.dtype.lower().startswith(('int', 'uint')) else float(number)
                    if not math.isfinite(value): raise ValueError
                except (InvalidOperation, ValueError, OverflowError):
                    reason = 'invalid_numeric'; break
            elif not isinstance(value, str):
                reason = 'invalid_category'; break
            record[rule.name] = value
        if reason is None and outside_range:
            reason = 'outside_training_range'
        if reason:
            rejected[reason] += 1
        else:
            accepted.append(row); payload.append(record)
    return accepted, payload, rejected


def checked_predictions(result: dict, model: dict, payload: list[dict]) -> list[float]:
    """Require exact row identity, not zip() against potentially dropped/reordered rows."""
    if not isinstance(result, dict):
        raise IntegrationError('API returned an invalid prediction response.')
    if result.get('model_id') != model['id'] or result.get('prediction_column') != model['prediction_column']:
        raise IntegrationError('API returned an unexpected model or prediction column.')
    records = result.get('records', [])
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise IntegrationError('API returned an invalid prediction-record structure.')
    if 'out_of_range_rows' not in result:
        raise IntegrationError('API lacks training-range response metadata; update/restart the local API or rebuild the Docker deployment first.')
    if type(result.get('out_of_range_rows')) is not int or result['out_of_range_rows'] != 0:
        raise IntegrationError('API training-range filtering differed from preview; no results for this batch were written.')
    if result.get('dropped_rows') != 0 or len(records) != len(payload):
        raise IntegrationError('API dropped rows or changed row count; refusing to associate predictions with wrong timestamps.')
    expected = [row[ROW_KEY] for row in payload]
    if len(set(expected)) != len(expected) or [row.get(ROW_KEY) for row in records] != expected:
        raise IntegrationError('API row identity/order mismatch; no results for this batch were written.')
    predictions = []
    for row in records:
        value = row.get(model['prediction_column'])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise IntegrationError('API returned a nonfinite/nonnumeric prediction.')
        predictions.append(float(value))
    return predictions


def schema_definition(columns: list[dict]):
    fields = [column['Field'] for column in columns]
    if 'timestamp' not in fields or set(fields) & set(EXTRA_COLUMNS):
        raise IntegrationError('Source timestamp missing or source columns conflict with result fields.')
    result = []
    for column in columns:
        name, kind, nullable = column['Field'], column['Type'].lower(), column['Null'] == 'YES'
        extra = column.get('Extra', '').strip().lower()
        # Copy source audit timestamps as values, not as auto-updating target columns.
        allowed_extra = re.fullmatch(r'(?:default_generated)?(?:\s*on update current_timestamp(?:\([0-6]\))?)?', extra)
        if not MYSQL_TYPE.fullmatch(kind) or not allowed_extra:
            raise IntegrationError(f'Unsupported source column type/extra; review schema before copying: {name}')
        if name == 'timestamp' and (nullable or not kind.startswith('datetime')):
            raise IntegrationError('Source timestamp must be a non-null DATETIME key.')
        result.append((name, kind, nullable))
    return result + [('actual_value', 'double', True), ('prediction_value', 'double', False),
                     ('model_id', 'varchar(128)', False), ('predicted_at', 'datetime(6)', False)]


def create_target_sql(database: str, table: str, definition: list[tuple]) -> str:
    columns = ', '.join(f'{quoted(name)} {kind} ' + ('NULL' if nullable else 'NOT NULL') for name, kind, nullable in definition)
    return (f'CREATE TABLE {table_path(database, table)} ({columns}, PRIMARY KEY (`timestamp`, `model_id`)) '
            'ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin')


def ensure_target(connection, args, columns: list[dict]):
    definition = schema_definition(columns)
    with connection.cursor() as cursor:
        cursor.execute('SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE FROM information_schema.COLUMNS '
            'WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION', (args.target_db, args.target_table))
        existing = cursor.fetchall()
        if not existing:
            if not args.init_target:
                raise IntegrationError('Target table missing; first write requires --init-target (or operator-created schema).')
            cursor.execute(f'CREATE DATABASE IF NOT EXISTS {quoted(args.target_db)} CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
            cursor.execute(create_target_sql(args.target_db, args.target_table, definition))
        else:
            actual = [(c['COLUMN_NAME'], c['COLUMN_TYPE'].lower(), c['IS_NULLABLE'] == 'YES') for c in existing]
            if actual != definition:
                raise IntegrationError('Existing target schema differs; refusing to alter/overwrite it automatically.')
        cursor.execute('SELECT COLUMN_NAME FROM information_schema.STATISTICS '
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME='PRIMARY' ORDER BY SEQ_IN_INDEX",
            (args.target_db, args.target_table))
        if [row['COLUMN_NAME'] for row in cursor.fetchall()] != ['timestamp', 'model_id']:
            raise IntegrationError('Target must have primary key (timestamp, model_id) to protect repeat runs and measured values.')
        cursor.execute('SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',
            (args.target_db, args.target_table))
        if cursor.fetchone()['ENGINE'].lower() != 'innodb':
            raise IntegrationError('Target must use transactional InnoDB storage.')


def source_query(args, after: datetime | None, size: int, upper_bound: datetime | None = None):
    source = table_path(args.source_db, args.source_table)
    conditions, parameters = [], []
    for bound, operator in ((after, '>'), (args.timestamp_from, '>='), (args.timestamp_to, '<'), (upper_bound, '<=')):
        if bound is not None:
            conditions.append(f's.`timestamp` {operator} %s'); parameters.append(bound)
    if args.mode == 'write':
        target = table_path(args.target_db, args.target_table)
        conditions.append(f'NOT EXISTS (SELECT 1 FROM {target} p WHERE p.`timestamp`=s.`timestamp` AND p.`model_id`=%s)')
        parameters.append(args.model_id)
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    return f'SELECT s.* FROM {source} s{where} ORDER BY s.`timestamp` LIMIT %s', (*parameters, size)


def write_batch(connection, args, columns, rows, predictions):
    names = [column['Field'] for column in columns] + list(EXTRA_COLUMNS)
    sql = (f'INSERT INTO {table_path(args.target_db, args.target_table)} ({", ".join(map(quoted, names))}) '
           f'VALUES ({", ".join(["%s"] * len(names))}) ON DUPLICATE KEY UPDATE `model_id`=`model_id`')
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    values = [tuple(row[column['Field']] for column in columns) + (None, prediction, args.model_id, now)
              for row, prediction in zip(rows, predictions, strict=True)]
    connection.begin()
    try:
        with connection.cursor() as cursor:
            cursor.executemany(sql, values)
            inserted = cursor.rowcount
        connection.commit()
        return inserted
    except Exception:
        connection.rollback()
        raise


def run(connection, client, args):
    model, snapshot = client.model_and_ranges(args.model_id)
    with connection.cursor() as cursor:
        cursor.execute(f'SHOW COLUMNS FROM {table_path(args.source_db, args.source_table)}')
        columns = cursor.fetchall()
        cursor.execute(f'SELECT `name_zh`, `column_name` FROM {table_path(args.source_db, args.mapping_table)} ORDER BY `ordinal`')
        mappings = cursor.fetchall()
        cursor.execute('SELECT COLUMN_NAME FROM information_schema.STATISTICS '
            "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME='PRIMARY' ORDER BY SEQ_IN_INDEX",
            (args.source_db, args.source_table))
        if [row['COLUMN_NAME'] for row in cursor.fetchall()] != ['timestamp']:
            raise IntegrationError('Source must have its unique timestamp primary key for stable paging.')
        cursor.execute(f'SELECT MAX(`timestamp`) AS upper_bound FROM {table_path(args.source_db, args.source_table)}')
        upper_bound = cursor.fetchone()['upper_bound']
        if upper_bound is not None and (not isinstance(upper_bound, datetime) or upper_bound.tzinfo is not None):
            raise IntegrationError('Source upper timestamp must be a source-local DATETIME.')
    rules = feature_rules(model, snapshot, mappings, columns, load_feature_aliases(args.feature_aliases))
    if args.mode == 'write': ensure_target(connection, args, columns)
    after, totals = None, Counter(read=0, eligible=0, predicted=0, inserted=0)
    # Bound this run so an actively growing source table cannot keep it running
    # indefinitely. This is a timestamp high-water mark, not a DB snapshot lock.
    if upper_bound is None:
        return dict(totals)
    while args.limit is None or totals['read'] < args.limit:
        size = args.batch_size if args.limit is None else min(args.batch_size, args.limit - totals['read'])
        sql, parameters = source_query(args, after, size, upper_bound)
        with connection.cursor() as cursor:
            cursor.execute(sql, parameters); rows = cursor.fetchall()
        if not rows: break
        after = rows[-1]['timestamp']
        accepted, payload, rejected = prepare_batch(rows, rules)
        totals.update(rejected); totals['read'] += len(rows); totals['eligible'] += len(accepted)
        if payload and args.mode != 'preview':
            result = client.request('/predict/json', {'model_id': args.model_id, 'data': payload,
                'ground_truth_column': '', 'training_range_policy': 'drop'})
            predictions = checked_predictions(result, model, payload)
            totals['predicted'] += len(predictions)
            if args.mode == 'write': totals['inserted'] += write_batch(connection, args, columns, accepted, predictions)
        print(json.dumps({'mode': args.mode, **dict(totals)}, ensure_ascii=False))
    return dict(totals)


def parse_time(value: str):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is not None: raise ValueError
        return result
    except ValueError:
        raise argparse.ArgumentTypeError('Use a source-local datetime without a timezone, e.g. 2026-10-06T00:00:00.') from None


def parse_args(argv=None, *, require_time_range: bool = False):
    argv = list(sys.argv[1:] if argv is None else argv)
    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    config_args, _ = config_parser.parse_known_args(argv)
    parser = argparse.ArgumentParser(description=__doc__)
    try:
        # Help remains available even if a custom configuration is missing/broken.
        settings = PredictionSettings() if '--help' in argv or '-h' in argv else load_settings(config_args.config)
    except ConfigurationError as exc:
        parser.error(str(exc))
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG,
                        help='Non-secret INI settings; defaults to the INI next to this script. CLI overrides settings.')
    parser.add_argument('--env-file', type=Path,
                        help='Client credential file; default is examples/.env.local next to the script, never the Server .env.')
    parser.add_argument('--api-url', default=os.getenv('EDGEML_CLIENT_API_URL', settings.api_url))
    parser.add_argument('--model-id', default=os.getenv('EDGEML_MODEL_ID', settings.model_id))
    parser.add_argument('--api-timeout', type=float, default=settings.api_timeout, help='API timeout in seconds.')
    parser.add_argument('--host', default=os.getenv('DB_HOST', settings.host))
    parser.add_argument('--port', type=int, default=os.getenv('DB_PORT', settings.port))
    parser.add_argument('--user', default=os.getenv('DB_USER', settings.user))
    parser.add_argument('--db-connect-timeout', type=int, default=settings.db_connect_timeout)
    parser.add_argument('--db-read-timeout', type=int, default=settings.db_read_timeout)
    parser.add_argument('--db-write-timeout', type=int, default=settings.db_write_timeout)
    parser.add_argument('--source-db', default=settings.source_db)
    parser.add_argument('--target-db', default=settings.target_db)
    parser.add_argument('--source-table', default=settings.source_table)
    parser.add_argument('--target-table', default=settings.target_table)
    parser.add_argument('--mapping-table', default=settings.mapping_table)
    parser.add_argument('--feature-aliases', type=Path,
        default=settings.feature_aliases,
        help='JSON model-feature -> DB mapping-name aliases; exact DB names take priority. Shared by both entrypoints.')
    parser.add_argument('--mode', choices=('preview', 'predict', 'write'), default='preview')
    parser.add_argument('--init-target', action='store_true', help='Explicitly create the missing destination database/table; never alter existing tables.')
    parser.add_argument('--batch-size', type=int, default=settings.batch_size)
    parser.add_argument('--limit', type=int, default=settings.limit,
                        help='Optional maximum source rows examined; empty INI limit means all rows, in batches.')
    parser.add_argument('--timestamp-from', type=parse_time, required=require_time_range,
                        help='Inclusive source-local lower timestamp bound.')
    parser.add_argument('--timestamp-to', type=parse_time, required=require_time_range,
                        help='Exclusive source-local upper timestamp bound.')
    args = parser.parse_args(argv)
    if not args.model_id.strip() or not 1 <= len(args.model_id) <= 128: parser.error('model-id must contain 1..128 characters.')
    if args.source_db == args.target_db: parser.error('Source and destination databases must differ.')
    if not 1 <= args.batch_size <= 10000 or (args.limit is not None and args.limit < 1) or not 1 <= args.port <= 65535:
        parser.error('Batch size must be 1..10000; limit and port must be valid positive values.')
    if not math.isfinite(args.api_timeout) or args.api_timeout <= 0 or min(
        args.db_connect_timeout, args.db_read_timeout, args.db_write_timeout
    ) <= 0:
        parser.error('Timeouts must be finite positive seconds.')
    if not args.host.strip() or not args.user.strip(): parser.error('MySQL host and user cannot be empty.')
    try:
        EdgeClient(args.api_url, '')  # Validate without connecting or asking for secrets.
    except IntegrationError as exc:
        parser.error(str(exc))
    if args.init_target and args.mode != 'write': parser.error('--init-target requires --mode write.')
    if args.timestamp_from and args.timestamp_to and args.timestamp_from >= args.timestamp_to:
        parser.error('timestamp-from must be before timestamp-to.')
    try:
        for name in (args.source_db, args.target_db, args.source_table, args.target_table, args.mapping_table): quoted(name)
    except IntegrationError as exc:
        parser.error(str(exc))
    return args


def main(argv=None, *, require_time_range: bool = False):
    args = parse_args(argv, require_time_range=require_time_range)
    try:
        import pymysql
    except ImportError:
        print('Install examples/requirements-piapifd.txt first.', file=sys.stderr); return 1
    connection = None
    try:
        secrets = load_client_secrets(args.env_file or DEFAULT_ENV_FILE, required=args.env_file is not None)
        token = os.getenv('EDGEML_CLIENT_API_TOKEN') or secrets.api_token or getpass.getpass('EdgeML API token: ')
        password = os.getenv('DB_PASSWORD') or secrets.db_password or getpass.getpass('MySQL password: ')
        if not token: raise IntegrationError('An EdgeML API token is required.')
        client = EdgeClient(args.api_url, token, timeout=args.api_timeout)
        connection = pymysql.connect(host=args.host, port=args.port, user=args.user, password=password,
            charset='utf8mb4', autocommit=True, cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=args.db_connect_timeout, read_timeout=args.db_read_timeout, write_timeout=args.db_write_timeout)
        totals = run(connection, client, args)
        print(json.dumps({'completed': True, 'mode': args.mode, **totals}, ensure_ascii=False))
        return 0
    except (ConfigurationError, IntegrationError) as exc:
        print(str(exc), file=sys.stderr); return 1
    except pymysql.MySQLError as exc:
        code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else 'unknown'
        print(f'MySQL operation failed (code {code}); completed batches remain saved. Credentials/row values omitted.', file=sys.stderr)
        return 1
    finally:
        if connection is not None: connection.close()


if __name__ == '__main__':
    sys.exit(main())
