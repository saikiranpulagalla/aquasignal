from types import SimpleNamespace

from signallock.providers.adaption_dataset import build_localization_dataset, run_adaption_localization


class FakeDatasets:
    def __init__(self, events):
        self.events = events
        self.upload = SimpleNamespace(complete_by_id=self.complete)
        self.status_calls = 0

    def create(self, **kwargs):
        self.events.append("create")
        return SimpleNamespace(dataset_id="d1", upload_instructions=SimpleNamespace(url="https://upload"))

    def complete(self, dataset_id, **kwargs):
        self.events.append("complete")

    def get_status(self, dataset_id):
        self.status_calls += 1
        self.events.append("status")
        return SimpleNamespace(status="awaiting_input", row_count=2, error_data=None)

    def run(self, dataset_id, **kwargs):
        self.events.append("run")
        return SimpleNamespace(run_id="r1")

    def wait_for_completion(self, dataset_id, timeout):
        self.events.append("wait")
        return SimpleNamespace(status="succeeded", error_data=None)

    def download(self, dataset_id):
        self.events.append("download")
        return "https://download"

    def get(self, dataset_id):
        self.events.append("get")
        return SimpleNamespace(evaluation_summary=None)


class FakeClient:
    def __init__(self, events):
        self.datasets = FakeDatasets(events)


def test_adaption_waits_for_ingestion_before_run(tmp_path):
    path = build_localization_dataset([{"text": "Shelter indoors."}], tmp_path / "a.csv")
    events = []
    result = run_adaption_localization(
        path,
        client=FakeClient(events),
        uploader=lambda url, data: events.append("upload"),
        poll_seconds=0,
    )
    assert events.index("status") < events.index("run")
    assert events == ["create", "upload", "complete", "status", "run", "wait", "download", "get"]
    assert result.dataset_id == "d1"
    assert result.run_id == "r1"
