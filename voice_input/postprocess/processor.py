from __future__ import annotations

import re


class TextPostProcessor:
    def __init__(self, append_final_punctuation: bool = True) -> None:
        self.append_final_punctuation = append_final_punctuation

    def process(self, text: str) -> str:
        value = text.strip()
        if not value:
            return ""
        value = self._remove_fillers(value)
        value = self._normalize_punctuation(value)
        if self.append_final_punctuation:
            value = self._ensure_sentence_punctuation(value)
        else:
            value = self._strip_final_period(value)
        return value.strip()

    def _remove_fillers(self, text: str) -> str:
        value = text.strip()
        value = re.sub(r"^(嗯+|呃+|额+|啊+)[，,、\s]*", "", value)
        value = re.sub(r"[，,、\s]+(嗯+|呃+|额+|啊+)[，,、\s]+", "，", value)
        value = re.sub(r"\b(um+|uh+|er+|ah+)\b[,\s]*", "", value, flags=re.IGNORECASE)
        value = re.sub(r"\s+", " ", value)
        return value.strip(" ，,、")

    def _normalize_punctuation(self, text: str) -> str:
        value = text.strip()
        if _contains_cjk(value):
            table = str.maketrans(
                {
                    ",": "，",
                    "?": "？",
                    "!": "！",
                    ";": "；",
                    ":": "：",
                }
            )
            value = value.translate(table)
            value = re.sub(r"\s*([，。！？；：])\s*", r"\1", value)
        return value

    def _ensure_sentence_punctuation(self, text: str) -> str:
        value = text.strip()
        if not value:
            return ""
        if value[-1] in "。！？!?；;：:，,.":
            if value[-1] in "，,；;：:":
                return value[:-1] + ("。" if _contains_cjk(value) else ".")
            return value
        return value + ("。" if _contains_cjk(value) else ".")

    def _strip_final_period(self, text: str) -> str:
        value = text.strip()
        if not value:
            return ""
        index = len(value) - 1
        while index >= 0 and value[index] in _TRAILING_CLOSERS:
            index -= 1
        if index >= 0 and value[index] in _FINAL_PERIODS:
            value = value[:index] + value[index + 1 :]
        return value


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


_FINAL_PERIODS = {"。", ".", "．"}
_TRAILING_CLOSERS = set("\"'”’）)]】》」』")
