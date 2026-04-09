"""
RedditPilot Business (Client) Manager with hot-reload and CRUD operations.

Adapted from MiloAgent's BusinessManager for RedditPilot's dataclass-based
Config system.  Watches a single YAML config file (not a directory of files)
and provides thread-safe client/account access with hot-reload callbacks.

Features:
  - Watch config YAML for changes via mtime polling (configurable interval)
  - Hot-reload clients/accounts when the file changes on disk
  - Thread-safe client and account list access
  - on_reload() callback system
  - CRUD operations for clients (add_client, update_client, remove_client)
  - Persist changes back to the YAML config file
  - Sync new/changed clients to the database
"""

import os
import time
import logging
import threading
import dataclasses
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any

import yaml

from redditpilot.core.config import (
    Config,
    ClientProfile,
    RedditAccount,
    DEFAULT_CONFIG_PATH,
)

logger = logging.getLogger("redditpilot.business_manager")


def _dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert a dataclass (or list/dict of dataclasses) to plain dicts."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {k: _dataclass_to_dict(v) for k, v in dataclasses.asdict(obj).items()}
    if isinstance(obj, list):
        return [_dataclass_to_dict(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    return obj


class BusinessManager:
    """Manages RedditPilot clients/accounts with config hot-reload.

    Unlike MiloAgent (which watches a *directory* of per-project YAML files),
    RedditPilot keeps everything in a single config.yaml.  This manager polls
    that file's mtime and reloads the full Config when it changes.

    Thread-safety: all reads of ``clients`` / ``accounts`` / ``config`` go
    through a ``threading.Lock`` and return snapshot copies.
    """

    def __init__(
        self,
        config_path: Optional[str] = None,
        db: Optional[Any] = None,
        auto_load: bool = True,
    ):
        self._config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._db = db  # Optional Database instance for syncing
        self._config: Config = Config()
        self._file_mtime: float = 0.0
        self._lock = threading.Lock()
        self._watcher_thread: Optional[threading.Thread] = None
        self._watching = False
        self._on_reload_callbacks: List[Callable] = []

        if auto_load:
            self.reload()

    # ── Properties (thread-safe snapshots) ─────────────────────────────

    @property
    def config(self) -> Config:
        """Return the current Config object (snapshot under lock)."""
        with self._lock:
            return self._config

    @property
    def clients(self) -> List[ClientProfile]:
        """Thread-safe snapshot of the current client list."""
        with self._lock:
            return list(self._config.clients)

    @property
    def accounts(self) -> List[RedditAccount]:
        """Thread-safe snapshot of the current account list."""
        with self._lock:
            return list(self._config.accounts)

    @property
    def config_path(self) -> Path:
        return self._config_path

    # ── Reload ─────────────────────────────────────────────────────────

    def reload(self) -> Config:
        """Reload config from disk, update internal state, notify callbacks.

        Returns the newly-loaded Config.
        """
        try:
            new_config = Config.load(str(self._config_path))
        except Exception as exc:
            logger.error("Failed to load config from %s: %s", self._config_path, exc)
            return self._config  # keep previous config on failure

        try:
            mtime = self._config_path.stat().st_mtime
        except OSError:
            mtime = 0.0

        with self._lock:
            old_slugs = {c.slug for c in self._config.clients}
            new_slugs = {c.slug for c in new_config.clients}
            old_users = {a.username for a in self._config.accounts}
            new_users = {a.username for a in new_config.accounts}

            self._config = new_config
            self._file_mtime = mtime

        # Log changes
        added_clients = new_slugs - old_slugs
        removed_clients = old_slugs - new_slugs
        changed_clients = new_slugs & old_slugs  # may or may not have changed

        if added_clients:
            logger.info("Clients added: %s", added_clients)
        if removed_clients:
            logger.info("Clients removed: %s", removed_clients)
        if not added_clients and not removed_clients and old_slugs:
            logger.debug("Config reloaded, %d clients unchanged", len(new_slugs))
        elif not old_slugs and new_slugs:
            logger.info("Loaded %d client(s): %s", len(new_slugs), sorted(new_slugs))

        added_accounts = new_users - old_users
        removed_accounts = old_users - new_users
        if added_accounts:
            logger.info("Accounts added: %s", added_accounts)
        if removed_accounts:
            logger.info("Accounts removed: %s", removed_accounts)

        # Sync to database
        if self._db is not None:
            self._sync_clients_to_db(new_config.clients)
            self._sync_accounts_to_db(new_config.accounts)

        # Notify callbacks
        for cb in self._on_reload_callbacks:
            try:
                cb(new_config)
            except Exception as exc:
                logger.error("Reload callback error: %s", exc)

        return new_config

    # ── File Watcher ───────────────────────────────────────────────────

    def start_watching(self, interval: float = 5.0):
        """Start a daemon thread that polls config file mtime every *interval* seconds."""
        if self._watching:
            return
        self._watching = True
        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            args=(interval,),
            daemon=True,
            name="redditpilot-config-watcher",
        )
        self._watcher_thread.start()
        logger.info(
            "Config file watcher started (path=%s, interval=%.1fs)",
            self._config_path,
            interval,
        )

    def stop_watching(self):
        """Signal the watcher thread to stop (it will exit on next iteration)."""
        self._watching = False
        logger.info("Config file watcher stop requested")

    def _watch_loop(self, interval: float):
        """Poll mtime of the config file and reload when it changes."""
        while self._watching:
            time.sleep(interval)
            try:
                if not self._config_path.exists():
                    continue
                current_mtime = self._config_path.stat().st_mtime
                if current_mtime != self._file_mtime:
                    logger.info("Config file changed on disk, reloading...")
                    self.reload()
            except Exception as exc:
                logger.error("Config watcher error: %s", exc)

    # ── Callback Registration ──────────────────────────────────────────

    def on_reload(self, callback: Callable):
        """Register a callback invoked after every successful reload.

        Signature: ``callback(config: Config) -> None``
        """
        self._on_reload_callbacks.append(callback)

    def remove_on_reload(self, callback: Callable) -> bool:
        """Unregister a previously registered reload callback.

        Returns True if the callback was found and removed.
        """
        try:
            self._on_reload_callbacks.remove(callback)
            return True
        except ValueError:
            return False

    # ── CRUD: Clients ──────────────────────────────────────────────────

    def get_client(self, slug: str) -> Optional[ClientProfile]:
        """Get a client by slug (case-insensitive)."""
        slug_lower = slug.lower()
        for c in self.clients:
            if c.slug.lower() == slug_lower:
                return c
        return None

    def list_clients(self) -> List[str]:
        """Return list of all client slugs."""
        return [c.slug for c in self.clients]

    def add_client(
        self,
        name: str,
        slug: str,
        industry: str,
        service_area: str,
        *,
        website: str = "",
        brand_voice: str = "",
        target_subreddits: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        competitors: Optional[List[str]] = None,
        personas: Optional[List[dict]] = None,
        promo_ratio: float = 0.05,
        approval_required: bool = True,
        enabled: bool = True,
    ) -> ClientProfile:
        """Create a new client, persist to YAML, sync to DB.

        Raises ValueError if a client with the same slug already exists.
        Returns the created ClientProfile.
        """
        slug_clean = slug.lower().replace(" ", "_").replace("-", "_")

        with self._lock:
            existing_slugs = {c.slug.lower() for c in self._config.clients}
            if slug_clean in existing_slugs:
                raise ValueError(f"Client with slug '{slug_clean}' already exists")

            client = ClientProfile(
                name=name,
                slug=slug_clean,
                industry=industry,
                service_area=service_area,
                website=website,
                brand_voice=brand_voice,
                target_subreddits=target_subreddits or [],
                keywords=keywords or [],
                competitors=competitors or [],
                personas=personas or [],
                promo_ratio=promo_ratio,
                approval_required=approval_required,
                enabled=enabled,
            )
            self._config.clients.append(client)

        self._persist_config()

        if self._db is not None:
            self._sync_clients_to_db([client])

        logger.info("Added client '%s' (slug=%s)", name, slug_clean)

        # Notify callbacks with updated config
        for cb in self._on_reload_callbacks:
            try:
                cb(self._config)
            except Exception as exc:
                logger.error("Reload callback error after add_client: %s", exc)

        return client

    def update_client(self, slug: str, **updates) -> ClientProfile:
        """Update fields of an existing client, persist and sync.

        Raises KeyError if the slug is not found.
        Returns the updated ClientProfile.
        """
        slug_lower = slug.lower()

        with self._lock:
            target = None
            for c in self._config.clients:
                if c.slug.lower() == slug_lower:
                    target = c
                    break
            if target is None:
                raise KeyError(f"Client with slug '{slug}' not found")

            # Apply updates to the dataclass instance
            valid_fields = {f.name for f in dataclasses.fields(ClientProfile)}
            for key, value in updates.items():
                if key not in valid_fields:
                    raise ValueError(
                        f"Unknown ClientProfile field: '{key}'. "
                        f"Valid fields: {sorted(valid_fields)}"
                    )
                setattr(target, key, value)

        self._persist_config()

        if self._db is not None:
            self._sync_clients_to_db([target])

        logger.info("Updated client '%s': %s", slug, list(updates.keys()))

        for cb in self._on_reload_callbacks:
            try:
                cb(self._config)
            except Exception as exc:
                logger.error("Reload callback error after update_client: %s", exc)

        return target

    def remove_client(self, slug: str) -> bool:
        """Remove a client by slug.  Persists the change to YAML.

        Returns True if the client was found and removed, False otherwise.
        """
        slug_lower = slug.lower()

        with self._lock:
            before_len = len(self._config.clients)
            self._config.clients = [
                c for c in self._config.clients if c.slug.lower() != slug_lower
            ]
            removed = len(self._config.clients) < before_len

        if removed:
            self._persist_config()
            logger.info("Removed client '%s'", slug)

            for cb in self._on_reload_callbacks:
                try:
                    cb(self._config)
                except Exception as exc:
                    logger.error("Reload callback error after remove_client: %s", exc)
        else:
            logger.warning("Client '%s' not found for removal", slug)

        return removed

    # ── Persistence ────────────────────────────────────────────────────

    def _persist_config(self):
        """Serialize the current Config back to the YAML file.

        Creates parent directories if needed.  Uses an atomic-ish write
        (write to temp then rename) to avoid partial reads by the watcher.
        """
        self._config_path.parent.mkdir(parents=True, exist_ok=True)

        data = self._config_to_dict(self._config)

        tmp_path = self._config_path.with_suffix(".yaml.tmp")
        try:
            with open(tmp_path, "w") as fh:
                yaml.dump(data, fh, default_flow_style=False, sort_keys=False)
            tmp_path.replace(self._config_path)
        except Exception as exc:
            logger.error("Failed to persist config: %s", exc)
            # Clean up temp file on failure
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

        # Update our cached mtime so the watcher doesn't trigger a spurious reload
        try:
            self._file_mtime = self._config_path.stat().st_mtime
        except OSError:
            pass

        logger.debug("Config persisted to %s", self._config_path)

    @staticmethod
    def _config_to_dict(config: Config) -> dict:
        """Convert a Config dataclass tree into a plain dict suitable for YAML dump."""
        data: Dict[str, Any] = {}

        # Accounts
        data["accounts"] = [_dataclass_to_dict(a) for a in config.accounts]

        # Clients
        data["clients"] = [_dataclass_to_dict(c) for c in config.clients]

        # Sub-configs
        data["llm"] = _dataclass_to_dict(config.llm)
        data["safety"] = _dataclass_to_dict(config.safety)
        data["slack"] = _dataclass_to_dict(config.slack)

        # Top-level scalars
        data["data_dir"] = config.data_dir
        data["log_level"] = config.log_level
        data["scan_interval_minutes"] = config.scan_interval_minutes
        data["learning_interval_hours"] = config.learning_interval_hours

        return data

    # ── Database Sync ──────────────────────────────────────────────────

    def _sync_clients_to_db(self, clients: List[ClientProfile]):
        """Upsert client records into the database.

        Uses INSERT OR REPLACE keyed on the unique ``slug`` column.
        """
        if self._db is None:
            return

        for client in clients:
            try:
                existing = self._db.fetchone(
                    "SELECT id FROM clients WHERE slug = ?", (client.slug,)
                )
                if existing:
                    self._db._execute_write(
                        """UPDATE clients
                           SET name = ?, industry = ?, service_area = ?,
                               website = ?, brand_voice = ?, promo_ratio = ?,
                               enabled = ?
                         WHERE slug = ?""",
                        (
                            client.name,
                            client.industry,
                            client.service_area,
                            client.website,
                            client.brand_voice,
                            client.promo_ratio,
                            1 if client.enabled else 0,
                            client.slug,
                        ),
                    )
                    logger.debug("DB: updated client '%s'", client.slug)
                else:
                    self._db._execute_write(
                        """INSERT INTO clients
                           (name, slug, industry, service_area, website, brand_voice,
                            promo_ratio, enabled)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            client.name,
                            client.slug,
                            client.industry,
                            client.service_area,
                            client.website,
                            client.brand_voice,
                            client.promo_ratio,
                            1 if client.enabled else 0,
                        ),
                    )
                    logger.debug("DB: inserted client '%s'", client.slug)
            except Exception as exc:
                logger.error("DB sync error for client '%s': %s", client.slug, exc)

    def _sync_accounts_to_db(self, accounts: List[RedditAccount]):
        """Upsert account records into the database.

        Uses INSERT OR IGNORE + UPDATE keyed on the unique ``username`` column.
        Only syncs enabled accounts.
        """
        if self._db is None:
            return

        for account in accounts:
            try:
                existing = self._db.fetchone(
                    "SELECT id FROM accounts WHERE username = ?",
                    (account.username,),
                )
                if existing:
                    self._db._execute_write(
                        """UPDATE accounts
                           SET karma_tier = ?, enabled = ?, updated_at = datetime('now')
                         WHERE username = ?""",
                        (
                            account.karma_tier,
                            1 if account.enabled else 0,
                            account.username,
                        ),
                    )
                else:
                    self._db._execute_write(
                        """INSERT INTO accounts
                           (username, karma_tier, enabled)
                           VALUES (?, ?, ?)""",
                        (
                            account.username,
                            account.karma_tier,
                            1 if account.enabled else 0,
                        ),
                    )
            except Exception as exc:
                logger.error(
                    "DB sync error for account '%s': %s", account.username, exc
                )

    # ── Convenience ────────────────────────────────────────────────────

    def get_enabled_clients(self) -> List[ClientProfile]:
        """Return only enabled clients (thread-safe snapshot)."""
        return [c for c in self.clients if c.enabled]

    def get_enabled_accounts(self) -> List[RedditAccount]:
        """Return only enabled accounts (thread-safe snapshot)."""
        return [a for a in self.accounts if a.enabled]

    def set_database(self, db: Any):
        """Attach or replace the database instance used for syncing.

        Triggers an immediate sync of all current clients and accounts.
        """
        self._db = db
        self._sync_clients_to_db(self._config.clients)
        self._sync_accounts_to_db(self._config.accounts)
        logger.info("Database attached; synced %d clients, %d accounts",
                     len(self._config.clients), len(self._config.accounts))

    def __repr__(self) -> str:
        return (
            f"<BusinessManager path={self._config_path} "
            f"clients={len(self._config.clients)} "
            f"accounts={len(self._config.accounts)} "
            f"watching={self._watching}>"
        )
