from __future__ import annotations

from dataclasses import dataclass

from signallock.providers.openai_http import OpenAIResponsesProvider
from signallock.transforms.demo import DemoTransformer


@dataclass(slots=True)
class TransformationService:
    provider: str = "heuristic"

    async def transform(
        self,
        text: str,
        *,
        mode: str,
        language: str | None = None,
        source_language: str = "en",
        max_chars: int = 360,
    ) -> tuple[str, dict]:
        if self.provider == "openai":
            client = OpenAIResponsesProvider()
            out = await client.transform(text, mode=mode, language=language, max_chars=max_chars)
            output_language = language if mode == "translate" else source_language
            return out, {
                "provider": "openai",
                "model": client.model,
                "mode": mode,
                "source_language": source_language,
                "output_language": output_language,
            }
        demo = DemoTransformer()
        out = demo.transform(text, mode=mode, language=language, max_chars=max_chars)
        output_language = language if mode == "translate" else source_language
        return out, {
            "provider": "deterministic-demo",
            "mode": mode,
            "source_language": source_language,
            "output_language": output_language,
        }
