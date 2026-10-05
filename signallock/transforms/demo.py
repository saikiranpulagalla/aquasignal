from __future__ import annotations

import re


class DemoTransformer:
    """Deterministic transformer used in tests and zero-key demo mode."""

    def transform(self, text: str, *, mode: str, language: str | None = None, max_chars: int = 360) -> str:
        if mode == "simplify":
            replacements = {
                "residents": "people living in the area",
                "immediately": "right away",
                "remain": "stay",
            }
            out = text
            for src, dst in replacements.items():
                out = re.sub(rf"\b{re.escape(src)}\b", dst, out, flags=re.I)
            return out
        if mode == "sms":
            out = re.sub(r"\s+", " ", text).strip()
            if len(out) <= max_chars:
                return out
            # Never silently truncate safety text. Demo mode refuses instead.
            raise ValueError(f"Cannot safely compress deterministic demo text below {max_chars} characters")
        if mode == "translate":
            raise ValueError("Live multilingual translation requires an AI/Adaption provider; demo mode will not fake it")
        raise ValueError(f"Unsupported mode: {mode}")
