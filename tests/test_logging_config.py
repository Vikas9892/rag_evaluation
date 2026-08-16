"""Tests for the shared logging handlers.

Thirty-three modules call `get_logger(__name__)`. Each used to receive its own
`RotatingFileHandler` over the same path, so the file had thirty-three writers
and thirty-three independent rotation decisions. On Windows the losing writer
raises WinError 32 mid-run, which is how this was noticed.
"""

import logging
import logging.handlers

from config.logging_config import get_logger


def _file_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [
        h
        for h in logger.handlers
        if isinstance(h, (logging.handlers.RotatingFileHandler, logging.NullHandler))
    ]


class TestSharedHandlers:
    def test_every_logger_writes_through_the_same_file_handler(self):
        # The bug: one handler per logger means one lock per logger, and
        # rotation is only safe when a single lock owns the file.
        first = _file_handlers(get_logger("test.logging.one"))
        second = _file_handlers(get_logger("test.logging.two"))

        assert first and second
        assert first[0] is second[0]

    def test_the_console_handler_is_shared_too(self):
        one = get_logger("test.logging.three")
        two = get_logger("test.logging.four")

        streams = [
            [
                h
                for h in logger.handlers
                if isinstance(h, logging.StreamHandler)
                and not isinstance(h, logging.handlers.RotatingFileHandler)
            ]
            for logger in (one, two)
        ]
        assert streams[0][0] is streams[1][0]

    def test_a_logger_is_not_given_a_second_set_of_handlers(self):
        # Called twice for the same module, which happens on re-import.
        logger = get_logger("test.logging.five")
        count = len(logger.handlers)

        assert get_logger("test.logging.five").handlers == logger.handlers
        assert len(logger.handlers) == count

    def test_logging_does_not_raise(self, caplog):
        logger = get_logger("test.logging.six")
        logger.info("a message that must not blow up on any platform")
