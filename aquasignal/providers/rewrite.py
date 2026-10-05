from __future__ import annotations

from signallock.providers.openai_http import OpenAIResponsesProvider, ProviderError


class FreshwaterRewriteProvider:
    """Proposal-only freshwater rewrite provider.

    This component can suggest citizen-facing wording but is deliberately absent from
    the verification path. A model never certifies its own output.
    """

    def __init__(self) -> None:
        self._provider = OpenAIResponsesProvider()
        self.model = self._provider.model

    async def transform(self, text: str, *, mode: str = "simplify", max_chars: int = 360) -> str:
        constraints = (
            "Preserve every protective action and prohibition, named freshwater site, "
            "upstream/downstream relationship, time constraint, audience, quantity, condition, "
            "exception, and force-changing term such as must, may, only, or do not. "
            "Do not infer water safety, invent thresholds, add health advice, or add new operational facts."
        )
        if mode == "simplify":
            instruction = f"Rewrite this authoritative freshwater advisory in plain citizen-facing English. {constraints}"
        elif mode == "sms":
            instruction = f"Compress this authoritative freshwater advisory to at most {max_chars} characters. {constraints}"
        else:
            raise ValueError(f"Unsupported freshwater rewrite mode: {mode}")

        raw = await self._provider._request({
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": instruction + " Output only the proposed rewrite. Do not add explanations.",
                },
                {"role": "user", "content": text},
            ],
        })
        output = self._provider._output_text(raw).strip()
        if not output:
            raise ProviderError("Provider returned an empty rewrite")
        if mode == "sms" and len(output) > max_chars:
            raise ProviderError(f"SMS rewrite exceeded character limit: {len(output)} > {max_chars}")
        return output
