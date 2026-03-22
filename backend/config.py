"""
config.py — ClawGrowth configuration.

Configuration priority (highest to lowest):
  1. Environment variables (CLAWGROWTH_*)
  2. Config file (config.json in project root or DATA_DIR)
  3. Default values

Environment variables:
  CLAWGROWTH_DB_PATH        — SQLite database path (default: ~/.openclaw/clawgrowth/clawgrowth.db)
  CLAWGROWTH_OPENCLAW_ROOT  — OpenClaw root directory (default: ~/.openclaw)
  CLAWGROWTH_HOST           — API server host (default: 0.0.0.0)
  CLAWGROWTH_PORT           — API server port (default: 57178)
  CLAWGROWTH_SCHEDULER      — Enable scheduler (default: true)
  CLAWGROWTH_COLLECT_HOUR   — Hourly collection (default: true)
  CLAWGROWTH_CLEANUP_HOUR   — Cleanup hour, 0-23 (default: 3)
  CLAWGROWTH_TOOL_DAYS      — Days to keep tool logs (default: 7)
  CLAWGROWTH_CRON_DAYS      — Days to keep cron logs (default: 30)

Config file (config.json):
  {
    "openclaw_root": "~/.openclaw",
    "db_path": "",
    "host": "0.0.0.0",
    "port": 57178,
    "scheduler_enabled": true,
    "collect_hourly": true,
    "cleanup_hour": 3,
    "tool_retention_days": 7,
    "cron_retention_days": 30
  }
"""
import json
import os
from pathlib import Path
from typing import Any, Optional


BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Config file loading (loaded once at module import)
# ---------------------------------------------------------------------------

def _load_config_file() -> dict:
    """Load config from JSON file. Search order: project root, DATA_DIR."""
    # Try project root first (ClawGrowth/config.json)
    project_root = BASE_DIR.parent
    config_paths = [
        project_root / 'config.json',
        BASE_DIR / 'data' / 'config.json',
    ]
    
    for config_path in config_paths:
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
    return {}


_CONFIG_FILE_DATA = _load_config_file()


def _get_config(key: str, default: Any = None) -> Any:
    """Get config value from file."""
    return _CONFIG_FILE_DATA.get(key, default)


# ---------------------------------------------------------------------------
# Config helpers (env > file > default)
# ---------------------------------------------------------------------------

def _resolve_str(env_key: str, file_key: str, default: str) -> str:
    """Resolve string config: env > file > default."""
    env_val = os.environ.get(env_key, '')
    if env_val:
        return env_val
    file_val = _get_config(file_key)
    if file_val is not None:
        return str(file_val)
    return default


def _resolve_bool(env_key: str, file_key: str, default: bool) -> bool:
    """Resolve boolean config: env > file > default."""
    env_val = os.environ.get(env_key, '').lower()
    if env_val in ('0', 'false', 'no', 'off'):
        return False
    if env_val in ('1', 'true', 'yes', 'on'):
        return True
    file_val = _get_config(file_key)
    if file_val is not None:
        return bool(file_val)
    return default


def _resolve_int(env_key: str, file_key: str, default: int) -> int:
    """Resolve integer config: env > file > default."""
    env_val = os.environ.get(env_key, '')
    if env_val:
        try:
            return int(env_val)
        except ValueError:
            pass
    file_val = _get_config(file_key)
    if file_val is not None:
        try:
            return int(file_val)
        except (ValueError, TypeError):
            pass
    return default


def _resolve_path(env_key: str, file_key: str, default: Path) -> Path:
    """Resolve path config: env > file > default. Supports ~ expansion."""
    env_val = os.environ.get(env_key, '')
    if env_val:
        return Path(env_val).expanduser()
    file_val = _get_config(file_key)
    if file_val:
        return Path(file_val).expanduser()
    return default


# ---------------------------------------------------------------------------
# Core paths
# ---------------------------------------------------------------------------

OPENCLAW_ROOT = _resolve_path('CLAWGROWTH_OPENCLAW_ROOT', 'openclaw_root', Path.home() / '.openclaw')
DB_PATH = _resolve_path('CLAWGROWTH_DB_PATH', 'db_path', OPENCLAW_ROOT / 'clawgrowth' / 'clawgrowth.db')
AGENTS_DIR = OPENCLAW_ROOT / 'agents'
CRON_RUNS_DIR = OPENCLAW_ROOT / 'cron' / 'runs'
SUBAGENT_RUNS_FILE = OPENCLAW_ROOT / 'subagents' / 'runs.json'

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

HOST = _resolve_str('CLAWGROWTH_HOST', 'host', '0.0.0.0')
PORT = _resolve_int('CLAWGROWTH_PORT', 'port', 57178)
FRONTEND_PORT = _resolve_int('CLAWGROWTH_FRONTEND_PORT', 'frontend_port', 57177)
DEFAULT_AGENT_ID = _resolve_str('CLAWGROWTH_DEFAULT_AGENT', 'default_agent', 'main')

# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

SCHEDULER_ENABLED = _resolve_bool('CLAWGROWTH_SCHEDULER', 'scheduler_enabled', True)
COLLECT_HOURLY = _resolve_bool('CLAWGROWTH_COLLECT_HOUR', 'collect_hourly', True)
CLEANUP_HOUR = _resolve_int('CLAWGROWTH_CLEANUP_HOUR', 'cleanup_hour', 3)  # 03:00
TOOL_RETENTION_DAYS = _resolve_int('CLAWGROWTH_TOOL_DAYS', 'tool_retention_days', 7)
CRON_RETENTION_DAYS = _resolve_int('CLAWGROWTH_CRON_DAYS', 'cron_retention_days', 30)

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

import hashlib
import secrets

# Auth config file location (separate from main config, stores password hash)
DATA_DIR = _resolve_path('CLAWGROWTH_DATA_DIR', 'data_dir', BASE_DIR / 'data')
AUTH_CONFIG_FILE = DATA_DIR / 'config.json'
DEFAULT_PASSWORD = 'deepquest.cn'


def _hash_password(password: str) -> str:
    """Hash password with SHA256."""
    return hashlib.sha256(password.encode()).hexdigest()


def _load_auth_config() -> dict:
    """Load auth config from JSON file."""
    if AUTH_CONFIG_FILE.exists():
        try:
            with open(AUTH_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_auth_config(config: dict) -> None:
    """Save auth config to JSON file."""
    AUTH_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUTH_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)


def get_password_hash() -> str:
    """Get current password hash, initialize with default if not set."""
    # First check main config file for password_hash
    main_config_hash = _get_config('password_hash')
    if main_config_hash:
        return main_config_hash
    
    # Then check auth config file
    config = _load_auth_config()
    if 'password_hash' not in config:
        config['password_hash'] = _hash_password(DEFAULT_PASSWORD)
        _save_auth_config(config)
    return config['password_hash']


def verify_password(password: str) -> bool:
    """Verify password against stored hash."""
    return _hash_password(password) == get_password_hash()


def change_password(old_password: str, new_password: str) -> tuple:
    """
    Change password.
    Returns: (success: bool, message: str)
    """
    if not verify_password(old_password):
        return False, 'Invalid current password'
    if len(new_password) < 6:
        return False, 'New password must be at least 6 characters'
    
    config = _load_auth_config()
    config['password_hash'] = _hash_password(new_password)
    _save_auth_config(config)
    return True, 'Password changed successfully'


def generate_token() -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(32)


# Session tokens storage (in-memory, cleared on restart)
_active_tokens = set()


def create_session(password: str) -> tuple:
    """
    Create a session if password is correct.
    Returns: (success: bool, token_or_error: str)
    """
    if not verify_password(password):
        return False, 'Invalid password'
    token = generate_token()
    _active_tokens.add(token)
    return True, token


def verify_token(token: str) -> bool:
    """Verify if token is valid."""
    return token in _active_tokens


def revoke_token(token: str) -> None:
    """Revoke a session token."""
    _active_tokens.discard(token)
