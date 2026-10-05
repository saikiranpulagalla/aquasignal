import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from signallock.contracts.extractor import HeuristicExtractor
from signallock.verification.engine import VerificationEngine
from signallock.providers.openai_http import OpenAIResponsesProvider
from signallock.cap.parser import parse_cap_xml
from signallock.cap.verifier import verify_cap_alerts
from signallock.evaluation.holdout import HoldoutError, seal_v7_holdout_strict
from signallock.evaluation.v7 import evaluate_v7_gate
from signallock.evaluation.release import resolve_release_identity, runtime_tree_sha256, write_release_manifest

E=HeuristicExtractor(); V=VerificationEngine()

UNSAFE=[
('Residents must evacuate or must shelter indoors. Residents must avoid roads or must boil water.','Residents must evacuate or must avoid roads. Residents must shelter indoors or must boil water.'),
('Residents must turn off the gas supply, then boil water. Residents must avoid roads, then evacuate.','Residents must turn off the gas supply, then evacuate. Residents must avoid roads, then boil water.'),
('Residents are advised to evacuate.','Residents must evacuate.'),
('Residents are urged to evacuate.','Residents must evacuate.'),
('Residents can evacuate.','Residents must evacuate.'),
('Residents must evacuate after 6 PM and before 7 PM.','Residents must evacuate after 6 PM.'),
('Flash flood warning. Residents, head to higher ground immediately.','Flash flood warning. Residents are in danger immediately.'),
('Flood warning. Residents, disconnect electricity.','Flood warning. Residents face an electricity outage.'),
('Residents in Zone A must evacuate.','Residents in Zone B must evacuate.'),
('Residents in Gachibowli must evacuate.','Residents in Secunderabad must evacuate.'),
('Children must evacuate.','Adults must evacuate.'),
('Hospital patients must shelter indoors.','Hospital staff must shelter indoors.'),
]

SAFE=[
('Residents must evacuate and must avoid roads.','Residents must evacuate. Residents must avoid roads.'),
('Residents must evacuate by 6 PM.','Residents must evacuate no later than 6 PM.'),
('Residents must evacuate before 6 PM.','Residents must evacuate prior to 6 PM.'),
('Turn off the gas supply, then evacuate.','After turning off the gas supply, evacuate.'),
]

def test_third_order_unsafe_cases_all_block():
    assert [V.verify(E.extract(s),E.extract(c)).decision.value for s,c in UNSAFE] == ['BLOCK']*len(UNSAFE)

def test_third_order_safe_equivalences_all_pass():
    assert [V.verify(E.extract(s),E.extract(c)).decision.value for s,c in SAFE] == ['PASS']*len(SAFE)

async def _native(lang,text,atype,verb,obj,source,mod='MUST',top=None,deadline=None):
    action={'type':atype,'verb':verb,'object':obj,'destination':None,'condition':None,'deadline':deadline,'negated':False,
            'evidence':{'quote':text,'start_char':0,'end_char':len(text)},'modality':mod,'scoped_audience':[],'scoped_areas':[],
            'temporal_operator':top,'temporal_constraints':([] if not top else [{'operator':top,'time':deadline}]),
            'bound_quantities':[],'bound_exceptions':[],'sequence_group':None,'sequence_index':None,'logic_group':None,'logic_operator':'SINGLE'}
    payload={'schema_version':'1.0','language':lang,'hazard':None,'audience':[],'affected_areas':[],'required_actions':[action],
             'prohibited_actions':[],'urgency':'Unknown','severity':'Unknown','certainty':'Unknown','effective_at':None,'expires_at':None,
             'quantities':[],'exceptions':[],'unresolved_operational_text':[],'source_id':None}
    class Fake(OpenAIResponsesProvider):
        async def _request(self,_): return {'output':[{'content':[{'type':'output_text','text':json.dumps(payload,ensure_ascii=False)}]}]}
    cand=await Fake(api_key='x').extract_contract(text,language=lang)
    return V.verify(E.extract(source),cand),cand

@pytest.mark.asyncio
async def test_native_guard_accepts_supported_clean_actions_and_blocks_modality_time_lie():
    rows=[
      ('hi','सड़कों से बचें।','AVOID','avoid','roads','Avoid roads.'),
      ('te','రోడ్లను నివారించండి.','AVOID','avoid','roads','Avoid roads.'),
      ('hi','पर्याप्त पानी पिएं।','EXECUTE','drink','water','Drink water.'),
      ('te','తగినంత నీరు త్రాగండి.','EXECUTE','drink','water','Drink water.'),
    ]
    for args in rows:
        result,cand=await _native(*args)
        assert result.decision.value == 'PASS'
        assert not cand.unresolved_operational_text
    result,cand=await _native('hi','निवासी शाम 6 बजे के बाद बाहर निकल सकते हैं।','EVACUATE','evacuate',None,
                              'Residents must evacuate before 6 PM.','MUST','BEFORE','6 PM')
    assert result.decision.value == 'BLOCK'
    assert any('modality' in x and 'temporal' in x for x in cand.unresolved_operational_text)

def _info(instruction,area,cats=('Met',),headline='Flood danger',description='Original description',polygon=''):
    cats_xml=''.join(f'<category>{x}</category>' for x in cats); poly=f'<polygon>{polygon}</polygon>' if polygon else ''
    return f'<info><language>en</language>{cats_xml}<event>Flood</event><urgency>Immediate</urgency><severity>Severe</severity><certainty>Likely</certainty><headline>{headline}</headline><description>{description}</description><instruction>{instruction}</instruction><area><areaDesc>{area}</areaDesc>{poly}</area></info>'
def _cap(infos):
    return f'<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>A1</identifier><sender>alerts.example</sender><sent>2026-09-10T12:00:00+05:30</sent><status>Actual</status><msgType>Alert</msgType><scope>Public</scope>{infos}</alert>'
def _capdec(s,c):
    return verify_cap_alerts(parse_cap_xml(s,profile_strict=True),parse_cap_xml(c,profile_strict=True)).decision.value

def test_cap_semantic_change_blocks_and_equivalent_structure_passes():
    assert _capdec(_cap(_info('Residents must evacuate.','East Zone',description='Dam failure imminent')),
                   _cap(_info('Residents must evacuate.','East Zone',description='Minor drainage issue'))) == 'BLOCK'
    a=_info('Residents must evacuate.','East Zone'); b=_info('Residents must shelter indoors.','West Zone')
    assert _capdec(_cap(a+b),_cap(b+a)) == 'PASS'
    assert _capdec(_cap(_info('Residents must evacuate.','East Zone',cats=('Met','Safety'))),
                   _cap(_info('Residents must evacuate.','East Zone',cats=('Safety','Met')))) == 'PASS'
    p1='10,10 10,11 11,11 11,10 10,10'; p2='11,11 11,10 10,10 10,11 11,11'
    assert _capdec(_cap(_info('Residents must evacuate.','East Zone',polygon=p1)),
                   _cap(_info('Residents must evacuate.','East Zone',polygon=p2))) == 'PASS'

def test_v7_gate_rejects_three_known_unsafe_reviews():
    classes=['action_area','action_audience','quantity_exception_binding','modality','temporal','logic_sequence']
    metrics={'total':24,'dangerous_pass_rate':0.0,'unsafe_block_recall':0.75,'clean_pass_rate':1.0,'clean_block_rate':0.0,'exact_decision_accuracy':21/24,
             'quality':{'unique_sources':12,'unique_candidates':24,'reviewer_count':3,'fault_class_counts':{'clean':12,**{k:2 for k in classes}}},
             'dangerous_pass_by_fault_class':{k:{'total':2,'passes':0,'pass_rate':0.0} for k in classes},
             'by_language':{'hi':{'total':12,'expected_pass_total':6,'expected_block_total':6,'dangerous_pass_rate':0.0,'unsafe_block_recall':0.75,'clean_pass_rate':1.0},
                            'te':{'total':12,'expected_pass_total':6,'expected_block_total':6,'dangerous_pass_rate':0.0,'unsafe_block_recall':0.75,'clean_pass_rate':1.0}}}
    gate=evaluate_v7_gate(metrics)
    assert gate['passed'] is False
    assert any('BLOCK recall' in x for x in gate['reasons'])

def test_packaged_release_requires_external_trust_anchor(tmp_path,monkeypatch):
    root=tmp_path/'r'; root.mkdir(); (root/'signallock').mkdir(); (root/'signallock'/'x.py').write_text('x=1\n', encoding='utf-8')
    write_release_manifest(root,source_commit=None,release_id='r1')
    monkeypatch.delenv('SIGNALLOCK_TRUSTED_RUNTIME_SHA256',raising=False)
    state=resolve_release_identity(root)
    assert state['internally_consistent'] is True and state['clean'] is False
    monkeypatch.setenv('SIGNALLOCK_TRUSTED_RUNTIME_SHA256',runtime_tree_sha256(root))
    assert resolve_release_identity(root)['clean'] is True
