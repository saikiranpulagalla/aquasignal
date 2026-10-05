import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.evaluation import draft


class FakeExtractService:
    def __init__(self, provider): pass
    async def extract(self, text, *, language='en', source_id=None):
        return HeuristicExtractor().extract(text, language='en', source_id=source_id)


class FakeTransformService:
    def __init__(self, provider): pass
    async def transform(self, text, *, mode, language=None, source_language='en', max_chars=360):
        return f"[{language}] {text}", {"provider":"fake","output_language":language,"mode":mode}


@pytest.mark.asyncio
async def test_review_draft_is_clean_only_and_never_preapproved(monkeypatch):
    monkeypatch.setattr(draft, 'ExtractionService', FakeExtractService)
    monkeypatch.setattr(draft, 'TransformationService', FakeTransformService)
    seed = draft.SourceSeed(
        case_id='s1',
        text='Residents must shelter indoors until 6 PM. Do not enter the eastern underpass. Avoid roads with more than 30 cm of water, except emergency personnel.',
    )
    rows = await draft.generate_review_draft([seed], languages=['hi', 'te'], provider='openai')
    assert len(rows) == 2
    assert all(r['human_reviewed'] is False for r in rows)
    assert all(r['expected_decision'] == 'UNREVIEWED' for r in rows)
    assert all(r['expected_fault'] == 'CLEAN_TRANSLATION' for r in rows)
    assert {r['candidate_language'] for r in rows} == {'hi','te'}
