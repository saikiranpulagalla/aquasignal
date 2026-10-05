import pytest
from fastapi.testclient import TestClient
from apps.api.main import app

@pytest.mark.parametrize('template', [
    'Residents of Zone C {op} Zone D must evacuate.',
    'Residents {op} visitors must evacuate Zone C.',
    'Students {op} drivers must shelter indoors.',
    'Residents in Zone 3 {op} Zone 4 must shelter indoors.',
    'Residents must evacuate Zone C {op} Zone D.',
    'Residents of Zone C {op} Zone D must not evacuate.',
    'Residents of Zone C {op} Zone D may evacuate.',
    'Residents of Zone C {op} Zone D should evacuate.',
    'Residents of Zone C {op} Zone D must evacuate before 7 PM.',
])
def test_scope_disjunction_is_not_erased(template):
    client = TestClient(app)
    for before,after in [('and','or'), ('or','and')]:
        result=client.post('/api/verify',json={'source_text':template.format(op=before),
            'candidate_text':template.format(op=after), 'provider':'heuristic'})
        assert result.status_code == 200
        assert result.json()['decision'] != 'PASS'
