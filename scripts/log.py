"""
Structured logging for the SD-BKZ benchmark pipeline.

Logs to both console (human-readable) and a JSONL file (machine-parseable).
Every entry has: datetime, script, level, category, message, and optional
key-value context.

Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
Categories: validation, integrity, schema, timing, incident, sync, sweep

Usage:
    from log import get_logger

    log = get_logger("validate_seeds")
    log.info("starting", cat="validation", seeds=3141)
    log.warning("volume mismatch", cat="integrity", file="seed42.json", diff=0.05)
    log.error("missing key", cat="schema", file="seed99.json", key="advantage")
    log.incident("q3329 MGS instability", id=26, file="seed1.json")

Log file: results/logs/pipeline.jsonl (append-only, one JSON object per line)
"""
import datetime
import json
import logging
import os
import sys
import uuid

# JSONL log file location
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(_REPO_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "pipeline.jsonl")

# Custom level for known incidents (between WARNING and ERROR)
INCIDENT = 35
logging.addLevelName(INCIDENT, "INCIDENT")


# -- Correlation ID --------------------------------------------------------
# A short hex token attached to every event so a single end-to-end run
# (wrapper → runner → multiprocessing workers → subprocess re-entrants)
# groups in pipeline.jsonl analyses. On fork the workers inherit the
# parent's module state automatically. For subprocess re-entrants, set
# the BKZ_RUN_ID environment variable before launching child Python and
# the child will pick it up on import.
_RUN_ID = os.environ.get("BKZ_RUN_ID") or None


def new_run_id():
    """Generate a fresh 12-hex-char run id, set it module-globally
    AND export to the environment so any subprocess inherits it.
    Returns the new id."""
    global _RUN_ID
    _RUN_ID = uuid.uuid4().hex[:12]
    os.environ["BKZ_RUN_ID"] = _RUN_ID
    return _RUN_ID


def get_run_id():
    return _RUN_ID


def set_run_id(rid):
    """Override the run id (used by tests or by code that wants to
    join a previously-launched chain). Pass None to clear."""
    global _RUN_ID
    _RUN_ID = rid
    if rid is None:
        os.environ.pop("BKZ_RUN_ID", None)
    else:
        os.environ["BKZ_RUN_ID"] = rid


class JsonlHandler(logging.Handler):
    """Append structured JSON lines to a file."""

    def __init__(self, filepath):
        super().__init__()
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self.filepath = filepath

    def emit(self, record):
        entry = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "script": getattr(record, "script", record.name),
            "cat": getattr(record, "cat", "general"),
            "msg": record.getMessage(),
        }
        if _RUN_ID:
            entry["run_id"] = _RUN_ID
        # Merge any extra context
        ctx = getattr(record, "ctx", {})
        if ctx:
            entry["ctx"] = ctx
        try:
            with open(self.filepath, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            pass  # don't crash on log write failure


class ConsoleFormatter(logging.Formatter):
    """Human-readable console output with level prefixes."""

    PREFIXES = {
        "DEBUG": "  DBG ",
        "INFO": "  INF ",
        "WARNING": "  WRN ",
        "INCIDENT": "  INC ",
        "ERROR": "  ERR ",
        "CRITICAL": "  CRT ",
    }

    def format(self, record):
        prefix = self.PREFIXES.get(record.levelname, "  ??? ")
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        cat = getattr(record, "cat", "")
        cat_str = f"[{cat}] " if cat else ""
        ctx = getattr(record, "ctx", {})
        ctx_str = ""
        if ctx:
            ctx_str = " " + " ".join(f"{k}={v}" for k, v in ctx.items())
        return f"{ts}{prefix}{cat_str}{record.getMessage()}{ctx_str}"


class PipelineLogger:
    """Wrapper around stdlib logger with structured context support.

    All logging methods are guaranteed to never raise — if anything goes
    wrong (disk full, permissions, encoding, broken handler), the call
    silently swallows the exception. The calling script is never affected
    by logging failures.
    """

    def __init__(self, script_name):
        self.script = script_name
        try:
            self.logger = logging.getLogger(f"pipeline.{script_name}")
            self.logger.setLevel(logging.DEBUG)

            # Avoid duplicate handlers on repeated get_logger calls
            if not self.logger.handlers:
                # Console handler (INFO+)
                ch = logging.StreamHandler(sys.stderr)
                ch.setLevel(logging.INFO)
                ch.setFormatter(ConsoleFormatter())
                self.logger.addHandler(ch)

                # JSONL file handler (all levels)
                jh = JsonlHandler(LOG_FILE)
                jh.setLevel(logging.DEBUG)
                self.logger.addHandler(jh)
        except Exception:
            self.logger = None  # silently disable logging if init fails

    def _log(self, level, msg, cat="general", **ctx):
        if self.logger is None:
            return
        try:
            extra = {"script": self.script, "cat": cat, "ctx": ctx}
            self.logger.log(level, msg, extra=extra)
        except Exception:
            pass  # logging must never fail the calling script

    def debug(self, msg, cat="general", **ctx):
        self._log(logging.DEBUG, msg, cat=cat, **ctx)

    def info(self, msg, cat="general", **ctx):
        self._log(logging.INFO, msg, cat=cat, **ctx)

    def warning(self, msg, cat="general", **ctx):
        self._log(logging.WARNING, msg, cat=cat, **ctx)

    def error(self, msg, cat="general", **ctx):
        self._log(logging.ERROR, msg, cat=cat, **ctx)

    def critical(self, msg, cat="general", **ctx):
        self._log(logging.CRITICAL, msg, cat=cat, **ctx)

    def incident(self, msg, id=None, cat="incident", **ctx):
        """Log a known incident — severity between WARNING and ERROR."""
        if id is not None:
            ctx["incident_id"] = id
        self._log(INCIDENT, msg, cat=cat, **ctx)


class _NoopLogger:
    """Fallback logger that swallows all calls. Used if PipelineLogger fails."""
    def debug(self, *a, **k): pass
    def info(self, *a, **k): pass
    def warning(self, *a, **k): pass
    def error(self, *a, **k): pass
    def critical(self, *a, **k): pass
    def incident(self, *a, **k): pass


def get_logger(script_name):
    """Get a PipelineLogger for the given script.

    Always returns a logger object — if construction fails for any reason,
    returns a no-op logger that silently swallows all log calls. The
    calling script is guaranteed to never crash from a logging failure.
    """
    try:
        return PipelineLogger(script_name)
    except Exception:
        return _NoopLogger()
