from __future__ import annotations

import csv
import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class AdaptionUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class AdaptionLocalizationResult:
    dataset_id: str
    run_id: str | None
    status: str
    row_count: int | None
    download: Any | None
    evaluation_summary: Any | None = None


def build_localization_dataset(alerts: list[dict[str, str]], path: str | Path) -> Path:
    """Write an auditable prompt/completion CSV suitable for Adaptive Data."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["instruction", "response"])
        writer.writeheader()
        for row in alerts:
            writer.writerow({
                "instruction": "Localize this emergency alert while preserving every protective action and safety-critical fact: " + row["text"],
                "response": row.get("reference", row["text"]),
            })
    return path


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _default_uploader(url: str, data: bytes) -> None:
    import httpx
    with httpx.Client(timeout=60) as http:
        response = http.put(url, content=data)
        response.raise_for_status()


def _wait_until_ingested(client, dataset_id: str, *, timeout: float, poll_seconds: float) -> Any:
    deadline = time.monotonic() + timeout
    while True:
        status = client.datasets.get_status(dataset_id)
        state = str(getattr(status, "status", "")).casefold()
        if state == "failed":
            raise AdaptionUnavailable(f"Adaption dataset ingestion failed: {getattr(status, 'error_data', None)}")
        row_count = getattr(status, "row_count", None)
        # Current API exposes awaiting_input after ingestion and a populated row_count.
        if row_count is not None and row_count > 0:
            return status
        if time.monotonic() >= deadline:
            raise AdaptionUnavailable("Timed out waiting for Adaption dataset ingestion")
        time.sleep(poll_seconds)


def run_adaption_localization(
    csv_path: str | Path,
    *,
    languages: list[str] | None = None,
    sample_rate: float = 1.0,
    estimate_only: bool = False,
    ingest_timeout: float = 180.0,
    run_timeout: float = 3600.0,
    poll_seconds: float = 2.0,
    client=None,
    uploader: Callable[[str, bytes], None] | None = None,
):
    """Run a complete Adaptive Data localization lifecycle.

    Sequence: create -> upload -> complete -> wait for ingestion/row_count -> run ->
    wait for completion -> download handle. The safety-critical verifier never depends
    on this provider being available.
    """
    if client is None:
        try:
            from adaption import Adaption
        except Exception as exc:  # pragma: no cover - optional dependency
            raise AdaptionUnavailable("Install the `adaption` package to run sponsor localization") from exc
        if not os.getenv("ADAPTION_API_KEY"):
            raise AdaptionUnavailable("ADAPTION_API_KEY is not configured")
        client = Adaption()

    path = Path(csv_path)
    data = path.read_bytes()
    created = client.datasets.create(source={"name": path.name, "file_format": "csv"})
    if not getattr(created, "upload_instructions", None):
        raise AdaptionUnavailable("Adaption did not return upload instructions")

    upload = uploader or _default_uploader
    upload(created.upload_instructions.url, data)
    client.datasets.upload.complete_by_id(
        created.dataset_id,
        file_size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )

    ingested = _wait_until_ingested(
        client,
        created.dataset_id,
        timeout=ingest_timeout,
        poll_seconds=poll_seconds,
    )

    target_languages = languages or ["hi", "te"]
    run = client.datasets.run(
        created.dataset_id,
        column_mapping={"prompt": "instruction", "completion": "response"},
        language_expansion={"type": "translate", "sample_rate": sample_rate, "languages": target_languages},
        brand_controls={
            "length": "concise",
            "blueprint": (
                "Emergency alert localization. Preserve protective actions, prohibitions, negation, locations, "
                "numbers, units, times, audiences, exceptions, urgency, severity, and certainty exactly in meaning."
            ),
        },
        job_specification={"max_rows": 100},
        estimate=estimate_only,
    )

    if estimate_only:
        return run

    final = client.datasets.wait_for_completion(created.dataset_id, timeout=run_timeout)
    final_state = str(getattr(final, "status", "")).casefold()
    if final_state == "failed":
        raise AdaptionUnavailable(f"Adaption localization failed: {getattr(final, 'error_data', None)}")
    if final_state not in {"succeeded", "ready"}:
        raise AdaptionUnavailable(f"Unexpected Adaption final status: {getattr(final, 'status', None)}")

    download = client.datasets.download(created.dataset_id)
    dataset = client.datasets.get(created.dataset_id)
    return AdaptionLocalizationResult(
        dataset_id=created.dataset_id,
        run_id=getattr(run, "run_id", None),
        status=str(getattr(final, "status", "succeeded")),
        row_count=getattr(ingested, "row_count", None),
        download=download,
        evaluation_summary=getattr(dataset, "evaluation_summary", None),
    )
