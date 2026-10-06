"""Typed, non-secret INI settings shared by the two prediction entrypoints."""
from __future__ import annotations

from configparser import ConfigParser, Error as IniError
from dataclasses import dataclass, replace
from pathlib import Path


DEFAULT_MODEL_ID = '67f88ae0-ad99-4f5c-b099-16a9c8059756'
DEFAULT_CONFIG = Path(__file__).with_name('piapifd_prediction.ini')
DEFAULT_ENV_FILE = Path(__file__).with_name('.env.local')


class ConfigurationError(ValueError):
    """Invalid client settings; messages must not contain configuration values."""


@dataclass(frozen=True, repr=False)
class ClientSecrets:
    api_token: str | None = None
    db_password: str | None = None


def load_client_secrets(path: Path, *, required: bool = False) -> ClientSecrets:
    """Read only this explicit file; never search for .env or modify os.environ.

    Use the pinned python-dotenv parser to preserve quoted passwords literally,
    reject malformed/duplicate entries, and avoid variable interpolation.
    Error messages and repr must never reveal the credential contents.
    """
    try:
        handle = path.open(encoding='utf-8-sig')
    except FileNotFoundError:
        if not required:
            return ClientSecrets()
        raise ConfigurationError('Client env file not found; check --env-file.') from None
    except OSError:
        raise ConfigurationError('Cannot read the client env file; check permissions.') from None
    with handle:
        try:
            from dotenv.parser import parse_stream
        except ImportError:
            raise ConfigurationError('Install examples/requirements-piapifd.txt to read the client env file.') from None
        values = {}
        try:
            for binding in parse_stream(handle):
                if binding.error:
                    raise ConfigurationError('Invalid client env syntax; check quoting and KEY=value format.')
                if binding.key is None:
                    continue
                if binding.key not in ('EDGEML_CLIENT_API_TOKEN', 'DB_PASSWORD'):
                    raise ConfigurationError('Client env accepts only EDGEML_CLIENT_API_TOKEN and DB_PASSWORD, not Server settings.')
                if binding.key in values:
                    raise ConfigurationError('Client env contains duplicate keys; keep one entry for each credential.')
                values[binding.key] = binding.value
        except (OSError, UnicodeError):
            raise ConfigurationError('Cannot read the client env file as UTF-8.') from None
    token = values.get('EDGEML_CLIENT_API_TOKEN')
    if token:
        token = token.strip()
        if any(ord(character) < 32 or ord(character) == 127 for character in token):
            raise ConfigurationError('The client API token must be a single line without control characters.')
    return ClientSecrets(api_token=token or None, db_password=values.get('DB_PASSWORD') or None)


@dataclass(frozen=True)
class PredictionSettings:
    api_url: str = 'http://127.0.0.1:8010/api'
    model_id: str = DEFAULT_MODEL_ID
    api_timeout: float = 60
    host: str = '127.0.0.1'
    port: int = 3306
    user: str = 'root'
    db_connect_timeout: int = 10
    db_read_timeout: int = 60
    db_write_timeout: int = 60
    source_db: str = 'piapi_fd'
    source_table: str = 'pidata1_merged'
    mapping_table: str = 'pidata1_mapping'
    target_db: str = 'piapifd_edge'
    target_table: str = 'pidata1_predict'
    batch_size: int = 200
    limit: int | None = None
    feature_aliases: Path = Path(__file__).with_name('piapifd_feature_aliases.json')


def optional_limit(value: str) -> int | None:
    return int(value) if value.strip() else None


# Explicit sections/keys detect typos rather than silently using defaults.
OPTIONS = {
    'api': {'url': ('api_url', str), 'model_id': ('model_id', str), 'timeout': ('api_timeout', float)},
    'mysql': {
        'host': ('host', str), 'port': ('port', int), 'user': ('user', str),
        'connect_timeout': ('db_connect_timeout', int), 'read_timeout': ('db_read_timeout', int),
        'write_timeout': ('db_write_timeout', int),
    },
    'source': {'database': ('source_db', str), 'table': ('source_table', str), 'mapping_table': ('mapping_table', str)},
    'target': {'database': ('target_db', str), 'table': ('target_table', str)},
    'prediction': {'batch_size': ('batch_size', int), 'limit': ('limit', optional_limit),
                   'feature_aliases': ('feature_aliases', Path)},
}


def load_settings(path: Path) -> PredictionSettings:
    parser = ConfigParser(interpolation=None, strict=True)
    try:
        with path.open(encoding='utf-8-sig') as handle:
            parser.read_file(handle)
    except (OSError, UnicodeError, IniError):
        raise ConfigurationError('Cannot read the client INI; check --config and its format.') from None
    if parser.defaults() or any(section not in OPTIONS for section in parser.sections()):
        raise ConfigurationError('Client INI has unknown sections or a disallowed DEFAULT section.')
    values = {}
    for section in parser.sections():
        for key, raw in parser.items(section):
            if key in ('token', 'api_token', 'password', 'db_password'):
                raise ConfigurationError('Do not store credentials in INI; use EDGEML_CLIENT_API_TOKEN and DB_PASSWORD or masked prompts.')
            if key not in OPTIONS[section]:
                raise ConfigurationError('Client INI has an unknown option; see piapifd_prediction.ini.')
            field, converter = OPTIONS[section][key]
            try:
                if not raw.strip() and field != 'limit':
                    raise ValueError
                value = converter(raw)
                if field == 'feature_aliases' and not value.is_absolute():
                    value = path.resolve().parent / value
                values[field] = value
            except (ValueError, TypeError):
                raise ConfigurationError(f'Invalid INI setting type: {section}.{key}.') from None
    return replace(PredictionSettings(), **values)
