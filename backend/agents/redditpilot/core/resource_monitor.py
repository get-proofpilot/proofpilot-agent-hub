"""System resource monitor for RedditPilot.

Monitors CPU, RAM, and disk usage. Automatically throttles the bot when
resources are constrained to prevent system slowdowns or OOM kills.

Cross-platform: optimized for Linux VPS (primary target) with macOS
fallbacks for local development. Auto-detects the platform at import time.

Adapted from MiloAgent's resource_monitor + environment detection, merged
into a single standalone module with no external dependencies beyond stdlib.

SAFETY FEATURES
---------------
- is_safe_to_proceed()  — gate check before any heavy operation (LLM calls,
  bulk Reddit API requests, content generation). Returns False when RAM or
  process RSS exceeds critical thresholds. Uses cached values for speed
  (< 1ms when cache is fresh).

- Threshold callbacks — register listeners via on_threshold(callback).
  Callbacks fire on events: ram_warn, ram_critical, cpu_warn, disk_warn,
  disk_critical, process_memory_warn, recovered. Useful for the orchestrator
  to pause/resume scheduling.

- throttle_factor — multiplier that increases when resources are strained.
  1.0 = normal, 2.0 = slow down 2x, 5.0 = near-paused. Orchestrator should
  multiply sleep/delay intervals by this value.

- Auto-GC — garbage collection is triggered automatically when RAM hits
  critical levels or process RSS exceeds the configured limit.

- get_status_dict() — returns a JSON-serializable dict of all metrics,
  suitable for a future dashboard/API endpoint.
"""

import functools
import gc
import logging
import os
import platform
import resource as _resource
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from typing import Callable, Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default thresholds (percentage). Overridden per-environment in __init__.
# ---------------------------------------------------------------------------
_DEFAULT_RAM_WARN = 80        # Start throttling
_DEFAULT_RAM_CRITICAL = 90    # Pause bot
_DEFAULT_DISK_WARN = 90       # Warn + cleanup
_DEFAULT_DISK_CRITICAL = 95   # Pause bot
_DEFAULT_CPU_WARN = 80        # Throttle scan frequency


# ---------------------------------------------------------------------------
# Inline environment detection (merged from MiloAgent's environment.py)
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def detect_environment() -> dict:
    """Detect runtime environment once and cache forever.

    Returns a dict with keys:
        os, arch, is_macos, is_linux, is_docker, is_headless,
        is_ssh, has_tty, hostname, cpu_count, is_server, recommended_mode

    On a Linux VPS this will typically yield:
        is_linux=True, is_server=True, is_headless=True
    """
    system = platform.system()
    info = {
        "os": system.lower(),                                   # "darwin" | "linux"
        "arch": platform.machine(),                             # "arm64" | "x86_64"
        "is_macos": system == "Darwin",
        "is_linux": system == "Linux",
        "is_docker": _is_docker(),
        "is_headless": not _has_display(),
        "is_ssh": "SSH_CLIENT" in os.environ or "SSH_TTY" in os.environ,
        "has_tty": sys.stdin.isatty() if hasattr(sys.stdin, "isatty") else False,
        "hostname": platform.node(),
        "cpu_count": os.cpu_count() or 1,
    }
    info["is_server"] = info["is_linux"] and (
        info["is_docker"] or info["is_headless"]
    )
    info["recommended_mode"] = (
        "server" if (info["is_server"] or info["is_docker"])
        else "full" if info["is_macos"]
        else "background"
    )
    return info


def _has_display() -> bool:
    """Check if a graphical display is available."""
    if platform.system() == "Darwin":
        return True  # macOS always has a virtual display
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _is_docker() -> bool:
    """Check if running inside a Docker/container environment."""
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "r") as f:
            content = f.read()
            return "docker" in content or "containerd" in content
    except (FileNotFoundError, PermissionError):
        return False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SystemState:
    """Point-in-time snapshot of system resource usage.

    All fields are JSON-serializable primitives so the dataclass can be
    converted via dataclasses.asdict() for API responses.
    """
    ram_total_gb: float = 0.0
    ram_used_percent: float = 0.0
    ram_available_gb: float = 0.0
    cpu_percent: float = 0.0
    cpu_cores: int = 1
    disk_total_gb: float = 0.0
    disk_free_gb: float = 0.0
    disk_used_percent: float = 0.0
    process_rss_mb: float = 0.0
    is_apple_silicon: bool = False
    cpu_name: str = "unknown"


# ---------------------------------------------------------------------------
# Resource Monitor
# ---------------------------------------------------------------------------

class ResourceMonitor:
    """Monitors system resources and auto-adapts RedditPilot behavior.

    Designed for a Linux VPS but falls back to macOS syscalls for local dev.

    Quick start::

        monitor = ResourceMonitor()
        monitor.start()                 # background thread every 30s

        if monitor.is_safe_to_proceed():
            do_heavy_work()
        else:
            logger.warning("Resources strained, skipping cycle")

        delay = base_delay * monitor.throttle_factor

    SAFETY FEATURES
    ----------------
    is_safe_to_proceed()
        Gate check before heavy operations. Uses cached RAM + RSS values
        (refreshed every 10 s) so the call itself is < 1 ms. Returns False
        and triggers gc.collect() when RAM >= critical or RSS > limit.

    throttle_factor (property)
        Float multiplier the orchestrator should apply to sleep intervals.
        1.0 = normal, 2.0 = under pressure, 5.0 = critical.

    on_threshold(callback)
        Register a ``callback(event: str, state: SystemState)`` that fires
        on resource events (ram_warn, ram_critical, cpu_warn, disk_warn,
        disk_critical, process_memory_warn, recovered).

    Auto-GC
        ``gc.collect()`` is called automatically when RAM hits critical or
        process RSS exceeds ``MAX_PROCESS_RSS_MB``.

    get_status_dict()
        Returns a JSON-serializable dict of all metrics plus environment
        info. Intended for a future dashboard REST/WebSocket API.
    """

    # Max RSS for this process before forced GC (MB).
    # Overridden to 500 MB on servers in _apply_env_config().
    MAX_PROCESS_RSS_MB: int = 400

    def __init__(self, check_interval: int = 30):
        """Initialise the resource monitor.

        Args:
            check_interval: Seconds between background monitoring cycles.
                            Default 30 s — fast enough to catch spikes before
                            the OOM killer does.
        """
        self._interval = check_interval
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._state = SystemState()
        self._callbacks: List[Callable] = []
        self._throttle_factor: float = 1.0   # 1.0 = normal, higher = slower
        self._last_ram_check: float = 0.0
        self._ram_cache_ttl: float = 10.0    # Cache RAM reads for 10 s

        # Per-instance thresholds (copied from defaults, mutated by _apply_env_config)
        self._ram_warn = _DEFAULT_RAM_WARN
        self._ram_critical = _DEFAULT_RAM_CRITICAL
        self._disk_warn = _DEFAULT_DISK_WARN
        self._disk_critical = _DEFAULT_DISK_CRITICAL
        self._cpu_warn = _DEFAULT_CPU_WARN

        # Detect environment (cached after first call)
        self._env: dict = detect_environment()

        # One-time hardware detection
        self._state.is_apple_silicon = self._detect_apple_silicon()
        self._state.cpu_name = self._detect_cpu_name()
        self._state.cpu_cores = os.cpu_count() or 1

        # Cache total RAM (doesn't change at runtime)
        self._total_ram_bytes: int = 0
        self._init_total_ram()

        # Environment-specific threshold overrides
        self._apply_env_config()

    # ------------------------------------------------------------------
    # Hardware detection (one-time)
    # ------------------------------------------------------------------

    def _init_total_ram(self) -> None:
        """Detect total physical RAM.

        macOS: ``sysctl -n hw.memsize``
        Linux: ``/proc/meminfo`` MemTotal line
        Fallback: assumes 8 GB.
        """
        try:
            if self._env["is_macos"]:
                result = subprocess.run(
                    ["sysctl", "-n", "hw.memsize"],
                    capture_output=True, text=True, timeout=3,
                )
                self._total_ram_bytes = int(result.stdout.strip())
            elif self._env["is_linux"]:
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemTotal:"):
                            self._total_ram_bytes = int(line.split()[1]) * 1024
                            break
            self._state.ram_total_gb = self._total_ram_bytes / (1024 ** 3)
        except Exception:
            self._total_ram_bytes = 8 * (1024 ** 3)
            self._state.ram_total_gb = 8.0

    def _detect_apple_silicon(self) -> bool:
        """Check if running on Apple Silicon (M-series)."""
        if not self._env["is_macos"]:
            return False
        try:
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=3,
            )
            return "Apple" in result.stdout
        except Exception:
            return False

    def _detect_cpu_name(self) -> str:
        """Get CPU model name.

        macOS: ``sysctl -n machdep.cpu.brand_string``
        Linux: first ``model name`` line from ``/proc/cpuinfo``
        """
        try:
            if self._env["is_macos"]:
                result = subprocess.run(
                    ["sysctl", "-n", "machdep.cpu.brand_string"],
                    capture_output=True, text=True, timeout=3,
                )
                return result.stdout.strip() if result.returncode == 0 else "unknown"
            elif self._env["is_linux"]:
                with open("/proc/cpuinfo") as f:
                    for line in f:
                        if "model name" in line:
                            return line.split(":", 1)[1].strip()
        except Exception:
            pass
        return "unknown"

    def _apply_env_config(self) -> None:
        """Tune thresholds for the detected environment.

        Servers (headless Linux / Docker) get relaxed limits because there
        is no desktop UI competing for resources. macOS keeps tighter limits
        to avoid Finder/browser sluggishness during development.
        """
        if self._env["is_server"]:
            self.MAX_PROCESS_RSS_MB = 500
            self._ram_warn = 85
            self._ram_critical = 95
            self._disk_warn = 92
            self._disk_critical = 97
            logger.info(
                "Resource monitor: server mode — relaxed thresholds "
                f"(RSS={self.MAX_PROCESS_RSS_MB}MB, RAM warn={self._ram_warn}%%, "
                f"RAM crit={self._ram_critical}%%)"
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def get_state(self) -> SystemState:
        """Return current system state after refreshing all metrics."""
        self._update_state()
        return self._state

    @property
    def throttle_factor(self) -> float:
        """Current throttle multiplier.

        1.0 = normal operation.
        2.0 = system under moderate pressure — double your delays.
        5.0 = critical — near-pause, only essential work should proceed.

        The orchestrator should multiply its base sleep/delay by this value.
        """
        return self._throttle_factor

    def is_safe_to_proceed(self) -> bool:
        """Quick gate check: is it safe to start a heavy operation?

        Call this before LLM prompts, bulk Reddit API calls, content
        generation, or any resource-intensive work.

        Behaviour:
        - Uses cached RAM + RSS values (refreshed every ``_ram_cache_ttl``
          seconds) so the call itself is < 1 ms in the fast path.
        - If RAM >= critical threshold → triggers ``gc.collect()`` → False.
        - If process RSS > ``MAX_PROCESS_RSS_MB`` → ``gc.collect()`` → False.
        - Otherwise → True.
        """
        now = time.monotonic()
        if now - self._last_ram_check > self._ram_cache_ttl:
            self._update_ram_fast()
            self._update_process_memory()
            self._last_ram_check = now

        if self._state.ram_used_percent >= self._ram_critical:
            gc.collect()
            return False
        if self._state.process_rss_mb > self.MAX_PROCESS_RSS_MB:
            gc.collect()
            return False
        return True

    def get_process_rss_mb(self) -> float:
        """Return current process RSS in megabytes."""
        self._update_process_memory()
        return self._state.process_rss_mb

    def on_threshold(self, callback: Callable) -> None:
        """Register a callback for resource threshold events.

        The callback signature is::

            def my_handler(event: str, state: SystemState) -> None: ...

        Possible events:
            ram_warn, ram_critical, cpu_warn, disk_warn, disk_critical,
            process_memory_warn, recovered
        """
        self._callbacks.append(callback)

    def start(self) -> None:
        """Start periodic background monitoring.

        Spawns a daemon thread that refreshes metrics every
        ``check_interval`` seconds and fires threshold callbacks.
        """
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="rp-resource-monitor",
        )
        self._thread.start()
        platform_label = "macOS" if self._env["is_macos"] else "Linux"
        server_tag = " [SERVER]" if self._env["is_server"] else ""
        logger.info(
            f"Resource monitor started: {platform_label}{server_tag}, "
            f"{self._state.cpu_name}, "
            f"{self._state.cpu_cores} cores, "
            f"{self._state.ram_total_gb:.1f} GB RAM, "
            f"RSS limit={self.MAX_PROCESS_RSS_MB} MB, "
            f"interval={self._interval}s"
        )

    def stop(self) -> None:
        """Stop the background monitoring thread."""
        self._running = False

    def get_status_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict of all resource metrics.

        Designed for a future dashboard REST / WebSocket API. Includes
        the full SystemState snapshot, current thresholds, throttle factor,
        environment info, and a boolean ``safe_to_proceed`` flag.

        Example return value::

            {
                "system": { ... SystemState fields ... },
                "thresholds": {
                    "ram_warn": 85,
                    "ram_critical": 95,
                    ...
                },
                "throttle_factor": 1.0,
                "safe_to_proceed": true,
                "environment": { ... detect_environment() dict ... },
                "timestamp": 1712345678.123
            }
        """
        self._update_state()
        return {
            "system": asdict(self._state),
            "thresholds": {
                "ram_warn": self._ram_warn,
                "ram_critical": self._ram_critical,
                "disk_warn": self._disk_warn,
                "disk_critical": self._disk_critical,
                "cpu_warn": self._cpu_warn,
                "max_process_rss_mb": self.MAX_PROCESS_RSS_MB,
            },
            "throttle_factor": self._throttle_factor,
            "safe_to_proceed": self.is_safe_to_proceed(),
            "environment": dict(self._env),  # copy so callers can't mutate cache
            "timestamp": time.time(),
        }

    def get_summary(self) -> str:
        """Return a human-readable multi-line summary of system state."""
        s = self._state
        env = self._env
        platform_label = "macOS" if env["is_macos"] else "Linux"
        if s.is_apple_silicon:
            cpu_label = "Apple Silicon"
        elif s.cpu_name != "unknown":
            cpu_label = s.cpu_name
        else:
            cpu_label = "unknown CPU"
        server_tag = " [SERVER]" if env["is_server"] else ""
        return (
            f"System: {platform_label} — {cpu_label} "
            f"({s.cpu_cores} cores){server_tag}\n"
            f"RAM: {s.ram_used_percent:.0f}% used "
            f"({s.ram_available_gb:.1f} GB available / {s.ram_total_gb:.1f} GB total)\n"
            f"Disk: {s.disk_used_percent:.0f}% used "
            f"({s.disk_free_gb:.0f} GB free / {s.disk_total_gb:.0f} GB total)\n"
            f"CPU: {s.cpu_percent:.0f}% load\n"
            f"Process RSS: {s.process_rss_mb:.0f} MB "
            f"(limit: {self.MAX_PROCESS_RSS_MB} MB)\n"
            f"Throttle: {self._throttle_factor}x"
        )

    # ------------------------------------------------------------------
    # Internal — background loop
    # ------------------------------------------------------------------

    def _monitor_loop(self) -> None:
        """Background monitoring loop (runs in daemon thread)."""
        while self._running:
            try:
                self._update_state()
                self._check_thresholds()
            except Exception as exc:
                logger.debug(f"Resource monitor tick error: {exc}")
            time.sleep(self._interval)

    # ------------------------------------------------------------------
    # Internal — state updates
    # ------------------------------------------------------------------

    def _update_state(self) -> None:
        """Refresh all system metrics."""
        self._update_ram()
        self._update_cpu()
        self._update_disk()
        self._update_process_memory()
        self._last_ram_check = time.monotonic()

    def _update_ram_fast(self) -> None:
        """Quick RAM check dispatched by platform."""
        if self._env["is_macos"]:
            self._update_ram_macos()
        elif self._env["is_linux"]:
            self._update_ram_linux()

    def _update_ram(self) -> None:
        """Full RAM update (alias for _update_ram_fast)."""
        self._update_ram_fast()

    def _update_ram_macos(self) -> None:
        """Parse ``vm_stat`` output for macOS RAM usage."""
        try:
            result = subprocess.run(
                ["vm_stat"], capture_output=True, text=True, timeout=3,
            )
            if result.returncode != 0:
                return

            lines = result.stdout.strip().split("\n")
            page_size = 4096
            if "page size of" in lines[0]:
                page_size = int(lines[0].split("page size of")[1].strip().split()[0])

            stats: Dict[str, int] = {}
            for line in lines[1:]:
                if ":" in line:
                    key, val = line.split(":", 1)
                    val = val.strip().rstrip(".")
                    try:
                        stats[key.strip()] = int(val)
                    except ValueError:
                        pass

            free = stats.get("Pages free", 0) * page_size
            active = stats.get("Pages active", 0) * page_size
            inactive = stats.get("Pages inactive", 0) * page_size
            speculative = stats.get("Pages speculative", 0) * page_size
            wired = stats.get("Pages wired down", 0) * page_size
            compressed = stats.get("Pages occupied by compressor", 0) * page_size

            total_used = active + wired + compressed
            total_available = free + inactive + speculative

            if self._total_ram_bytes > 0:
                self._state.ram_available_gb = total_available / (1024 ** 3)
                self._state.ram_used_percent = (total_used / self._total_ram_bytes) * 100
        except Exception:
            pass

    def _update_ram_linux(self) -> None:
        """Read ``/proc/meminfo`` for Linux RAM usage.

        Uses ``MemAvailable`` (kernel 3.14+) which accounts for reclaimable
        caches — much more accurate than ``MemFree`` alone.
        """
        try:
            meminfo: Dict[str, int] = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        meminfo[parts[0].rstrip(":")] = int(parts[1]) * 1024  # KB → bytes

            total = meminfo.get("MemTotal", 0)
            available = meminfo.get("MemAvailable", 0)
            if total > 0:
                used = total - available
                self._state.ram_available_gb = available / (1024 ** 3)
                self._state.ram_used_percent = (used / total) * 100
                self._total_ram_bytes = total
                self._state.ram_total_gb = total / (1024 ** 3)
        except Exception:
            pass

    def _update_cpu(self) -> None:
        """Compute CPU usage from POSIX load average.

        Uses 1-minute load average normalised by core count.  Works
        identically on macOS and Linux via ``os.getloadavg()``.
        """
        try:
            load1, _load5, _load15 = os.getloadavg()
            cores = self._state.cpu_cores or 1
            self._state.cpu_percent = min((load1 / cores) * 100, 100.0)
        except Exception:
            pass

    def _update_disk(self) -> None:
        """Check disk usage for the current working directory."""
        try:
            usage = shutil.disk_usage(os.getcwd())
            self._state.disk_total_gb = usage.total / (1024 ** 3)
            self._state.disk_free_gb = usage.free / (1024 ** 3)
            self._state.disk_used_percent = (usage.used / usage.total) * 100
        except Exception:
            pass

    def _update_process_memory(self) -> None:
        """Get current process RSS via ``resource.getrusage``.

        Note the platform difference:
        - macOS: ``ru_maxrss`` is in **bytes**
        - Linux: ``ru_maxrss`` is in **kilobytes**
        """
        try:
            rusage = _resource.getrusage(_resource.RUSAGE_SELF)
            if self._env["is_macos"]:
                self._state.process_rss_mb = rusage.ru_maxrss / (1024 * 1024)
            else:
                self._state.process_rss_mb = rusage.ru_maxrss / 1024
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Internal — threshold evaluation
    # ------------------------------------------------------------------

    def _check_thresholds(self) -> None:
        """Evaluate all thresholds and fire callbacks / adjust throttle.

        Called once per background loop tick. Adjusts ``_throttle_factor``
        and triggers ``gc.collect()`` when memory is critical.
        """
        old_factor = self._throttle_factor
        events: List[str] = []

        # --- RAM ---
        if self._state.ram_used_percent >= self._ram_critical:
            self._throttle_factor = 5.0
            events.append("ram_critical")
            gc.collect()
        elif self._state.ram_used_percent >= self._ram_warn:
            self._throttle_factor = 2.0
            events.append("ram_warn")
        else:
            self._throttle_factor = 1.0

        # --- CPU ---
        if self._state.cpu_percent >= self._cpu_warn:
            self._throttle_factor = max(self._throttle_factor, 2.0)
            events.append("cpu_warn")

        # --- Disk ---
        if self._state.disk_used_percent >= self._disk_critical:
            events.append("disk_critical")
        elif self._state.disk_used_percent >= self._disk_warn:
            events.append("disk_warn")

        # --- Process RSS ---
        if self._state.process_rss_mb > self.MAX_PROCESS_RSS_MB:
            events.append("process_memory_warn")
            gc.collect()

        # --- Recovery ---
        if old_factor > 1.0 and self._throttle_factor == 1.0:
            events.append("recovered")

        # --- Fire callbacks ---
        for event in events:
            for cb in self._callbacks:
                try:
                    cb(event, self._state)
                except Exception as exc:
                    logger.debug(f"Resource callback error: {exc}")

        # --- Log significant changes ---
        if events:
            logger.info(
                f"Resource: {', '.join(events)} | "
                f"RAM={self._state.ram_used_percent:.0f}% "
                f"CPU={self._state.cpu_percent:.0f}% "
                f"RSS={self._state.process_rss_mb:.0f}MB "
                f"throttle={self._throttle_factor}x"
            )
