"""Runtime containment helpers for per-session guardrails."""

import atexit
import contextlib
import errno
import json
import os
import signal
import tempfile
import uuid
from dataclasses import dataclass

try:  # POSIX-only file lock support.
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback.
    fcntl = None


RUNTIME_LIMIT_INT_KEYS = (
    "max_sessions_per_user",
    "max_background_jobs",
)

_DEFAULT_SESSION_STATE_ROOT = os.path.join(tempfile.gettempdir(), "lshell", "sessions")


@dataclass(frozen=True)
class RuntimeLimits:
    """Resolved runtime limits for one shell session."""

    max_sessions_per_user: int = 0
    max_background_jobs: int = 0


class ContainmentViolation(Exception):
    """Raised when a containment guardrail denies an action."""

    def __init__(self, reason_code, user_message, log_message):
        super().__init__(log_message)
        self.reason_code = reason_code
        self.user_message = user_message
        self.log_message = log_message


def reason_with_details(reason_code, **details):
    """Return a machine-readable reason with optional k=v details."""
    if not details:
        return reason_code
    ordered = ",".join(f"{key}={details[key]}" for key in sorted(details))
    return f"{reason_code} ({ordered})"


def _as_non_negative_int(conf, key):
    value = conf.get(key, 0)
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exception:
        raise ValueError(f"'{key}' must be an integer") from exception
    if parsed < 0:
        raise ValueError(f"'{key}' must be a non-negative integer")
    return parsed


def validate_runtime_config(conf):
    """Validate runtime containment keys from parsed config."""
    for key in RUNTIME_LIMIT_INT_KEYS:
        _as_non_negative_int(conf, key)


def get_runtime_limits(conf):
    """Return parsed runtime limits with disabled defaults."""
    return RuntimeLimits(
        max_sessions_per_user=_as_non_negative_int(conf, "max_sessions_per_user"),
        max_background_jobs=_as_non_negative_int(conf, "max_background_jobs"),
    )


def _session_state_root():
    configured = os.environ.get("LSHELL_SESSION_DIR")
    if configured:
        return configured
    return _DEFAULT_SESSION_STATE_ROOT


def _sanitize_component(value):
    safe = []
    for char in str(value or ""):
        if char.isalnum() or char in {".", "_", "-"}:
            safe.append(char)
        else:
            safe.append("_")
    sanitized = "".join(safe).strip("._")
    return sanitized or "unknown"


def _read_proc_start_time(pid):
    """Return process start time ticks from /proc when available."""
    stat_path = f"/proc/{pid}/stat"
    try:
        with open(stat_path, "r", encoding="utf-8") as handle:
            fields = handle.read().split()
    except OSError:
        return None

    if len(fields) < 22:
        return None
    return fields[21]


def _is_pid_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError as exception:
        if exception.errno == errno.ESRCH:
            return False
        if exception.errno == errno.EPERM:
            return True
        return False
    return True


def _matches_running_process(record):
    """Return True when record points to a still-running PID."""
    try:
        pid = int(record.get("pid", 0))
    except (TypeError, ValueError):
        return False

    if pid <= 0 or not _is_pid_alive(pid):
        return False

    expected_start = record.get("pid_start")
    if not expected_start:
        return True

    current_start = _read_proc_start_time(pid)
    if current_start is None:
        return True

    return str(expected_start) == str(current_start)


class SessionAccountant:
    """Track active shell sessions per user using lock-protected files."""

    def __init__(self, conf):
        self.conf = conf
        self.limits = get_runtime_limits(conf)
        self.username = str(conf.get("username") or os.environ.get("USER") or "unknown")
        self.session_id = str(conf.get("session_id") or uuid.uuid4().hex)
        self.state_root = _session_state_root()
        self.user_dir = os.path.join(self.state_root, _sanitize_component(self.username))
        self.session_file = os.path.join(
            self.user_dir,
            f"session-{_sanitize_component(self.session_id)}-{os.getpid()}.json",
        )
        self._registered = False
        self._previous_signal_handlers = {}

    @contextlib.contextmanager
    def _user_lock(self):
        os.makedirs(self.user_dir, mode=0o700, exist_ok=True)
        lock_path = os.path.join(self.user_dir, ".lock")
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def _read_session_record(self, path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError, ValueError):
            return None

    def _write_session_record(self):
        payload = {
            "pid": os.getpid(),
            "pid_start": _read_proc_start_time(os.getpid()),
            "session_id": self.session_id,
            "username": self.username,
        }
        with open(self.session_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)

    def _active_sessions_locked(self):
        active = []
        for entry in os.listdir(self.user_dir):
            if not (entry.startswith("session-") and entry.endswith(".json")):
                continue
            path = os.path.join(self.user_dir, entry)
            record = self._read_session_record(path)
            if not record or not _matches_running_process(record):
                with contextlib.suppress(OSError):
                    os.remove(path)
                continue
            active.append(path)
        return active

    def acquire(self):
        """Register this session and enforce max concurrent sessions per user."""
        max_sessions = self.limits.max_sessions_per_user
        if max_sessions <= 0:
            return

        with self._user_lock():
            active_sessions = self._active_sessions_locked()
            if len(active_sessions) >= max_sessions:
                reason = reason_with_details(
                    "runtime_limit.max_sessions_per_user_exceeded",
                    active=len(active_sessions),
                    limit=max_sessions,
                    user=self.username,
                )
                raise ContainmentViolation(
                    reason_code=reason,
                    user_message=(
                        "lshell: session denied: "
                        f"max_sessions_per_user={max_sessions} reached"
                    ),
                    log_message=(
                        "lshell: runtime containment denied session start: "
                        f"user={self.username}, active={len(active_sessions)}, "
                        f"limit={max_sessions}"
                    ),
                )
            self._write_session_record()

        if not self._registered:
            atexit.register(self.release)
            self._install_signal_handlers()
            self._registered = True

    def release(self):
        """Remove this session from accounting storage."""
        if self.limits.max_sessions_per_user <= 0:
            return

        if not self.session_file:
            return

        with contextlib.suppress(OSError):
            with self._user_lock():
                with contextlib.suppress(OSError):
                    os.remove(self.session_file)

        self._restore_signal_handlers()

    def _install_signal_handlers(self):
        for sig_name in ("SIGHUP", "SIGTERM", "SIGQUIT"):
            signum = getattr(signal, sig_name, None)
            if signum is None:
                continue
            previous = signal.getsignal(signum)
            self._previous_signal_handlers[signum] = previous
            signal.signal(signum, self._signal_cleanup_handler)

    def _restore_signal_handlers(self):
        for signum, previous in self._previous_signal_handlers.items():
            with contextlib.suppress(OSError, ValueError):
                signal.signal(signum, previous)
        self._previous_signal_handlers.clear()

    def _signal_cleanup_handler(self, signum, frame):
        self.release()
        previous = self._previous_signal_handlers.get(signum, signal.SIG_DFL)
        if callable(previous):
            previous(signum, frame)
            return
        if previous == signal.SIG_IGN:
            return
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
