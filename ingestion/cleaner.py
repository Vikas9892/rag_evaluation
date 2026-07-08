import re


class TextCleaner:
    """Normalises raw extracted text before it enters the pipeline."""

    def clean(self, text: str) -> str:
        text = self._remove_null_bytes(text)
        text = self._normalise_whitespace(text)
        text = self._remove_control_chars(text)
        return text.strip()

    def _remove_null_bytes(self, text: str) -> str:
        return text.replace("\x00", "")

    def _normalise_whitespace(self, text: str) -> str:
        # collapse runs of blanks / tabs into a single space,
        # but keep paragraph breaks (double newline)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text

    def _remove_control_chars(self, text: str) -> str:
        # keep printable chars + newline + tab
        return re.sub(r"[^\x09\x0A\x0D\x20-\x7E\x80-\xFF]", "", text)
