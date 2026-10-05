import pytest
from fastapi.testclient import TestClient
from apps.api.main import app

@pytest.mark.parametrize('noun',['Sector','Building','Shelter','District','County','Region','Block','Route'])
def test_unknown_named_scope_is_not_discarded(noun):
    result=TestClient(app).post('/api/verify',json={
        'source_text':f'Residents must evacuate {noun} 4.',
        'candidate_text':f'Residents must evacuate {noun} 5.'})
    assert result.status_code == 200
    assert result.json()['decision'] != 'PASS'

def test_unknown_geographic_subject_qualifier_is_not_discarded():
    client=TestClient(app)
    for _ in range(2):
        result=client.post('/api/verify',json={
            'source_text':'Residents of County Oak must shelter indoors.',
            'candidate_text':'Residents of County Pine must shelter indoors.'})
        assert result.json()['decision'] != 'PASS'
