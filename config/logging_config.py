"""Logging setup, shared by every module in the project.

**The handlers are created once and shared**, rather than per logger. Thirty-three
modules call `get_logger(__name__)`, and giving each its own
`RotatingFileHandler` over the same path meant thirty-three handlers, each with
its own lock and its own idea of when the file had reached 5 MB. On Windows
that surfaces as

    PermissionError: [WinError 32] The process cannot access the file because
    it is being used by another process: 'logs/ingestion.log' ->
    'logs/ingestion.log.1'

because one handler renames the file while the rest still hold it open. A
single handler serialises rotation through the one lock that owns the file.

Two processes writing the same log — a server and a test run, say — is still
outside what `RotatingFileHandler` can coordinate. Set `RAG_LOG_FILE` to give
one of them somewhere else to write.
"""

import logging
import logging.handlers
import os
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

#: Overridable so a second process can avoid contending for the same file.
LOG_FILE = Path(os.environ.get("RAG_LOG_FILE") or LOG_DIR / "ingestion.log")

_FORMAT = logging.Formatter(
    fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_console_handler: logging.Handler | None = None
_file_handler: logging.Handler | None = None


def _handlers() -> list[logging.Handler]:
    """The process's handlers, built on first use and reused thereafter."""
    global _console_handler, _file_handler

    if _console_handler is None:
        _console_handler = logging.StreamHandler()
        _console_handler.setLevel(logging.INFO)
        _console_handler.setFormatter(_FORMAT)

    if _file_handler is None:
        try:
            handler: logging.Handler = logging.handlers.RotatingFileHandler(
                LOG_FILE,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
                # Open on first write, not at import. A process that imports the
                # package without logging anything then holds no file open.
                delay=True,
            )
        except OSError:
            # A read-only or missing directory is a reason to lose the file log,
            # not a reason for the application to fail to start. Lambda's
            # filesystem is read-only outside /tmp.
            handler = logging.NullHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(_FORMAT)
        _file_handler = handler

    return [_console_handler, _file_handler]


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    for handler in _handlers():
        logger.addHandler(handler)

    logger.propagate = False
    return logger
