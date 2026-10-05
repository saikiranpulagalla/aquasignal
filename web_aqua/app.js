'use strict';

const $=id=>document.getElementById(id);
const source=$('sourceText'),candidate=$('candidateText');
let context=null;
let contextToken=null;
let frozen={sourceKey:null,contract:null,token:null};
let receipt=null;
let generation=0;
let contextGeneration=0;

const DEMOS={
  time:{source:'Visitors must avoid contact with Stream A after 18:00.',candidate:'Visitors must avoid contact with Stream A before 18:00.'},
  audience:{source:'Keep children and pets away from Stream A until 18:00.',candidate:'Keep children away from Stream A until 18:00.'},
  place:{source:'Avoid direct contact with stream water downstream of Bridge A until 18:00.',candidate:'Avoid direct contact with stream water upstream of Bridge A until 18:00.'},
  clean:{source:'Visitors must avoid contact with Stream A until 6 PM.',candidate:'Visitors must avoid contact with Stream A until 18:00.'},
  addition:{source:'Avoid direct contact with Stream A until 18:00.',candidate:'Avoid direct contact with Stream A until 18:00. Boil the water for at least 1 minute before drinking.'}
};

function esc(v){return String(v??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));}
function normalized(v){return v.toLowerCase().replace(/\s+/g,' ').trim();}
function similarity(a,b){a=normalized(a);b=normalized(b);if(a.length>2000||b.length>2000)return null;if(a===b)return 1;const n=a.length,m=b.length;if(!n||!m)return 0;let prev=Array.from({length:m+1},(_,i)=>i);for(let i=1;i<=n;i++){let cur=[i];for(let j=1;j<=m;j++){cur[j]=Math.min(cur[j-1]+1,prev[j]+1,prev[j-1]+(a[i-1]===b[j-1]?0:1));}prev=cur;}return 1-prev[m]/Math.max(n,m);}
function updateSimilarity(){const score=similarity(source.value,candidate.value);$('similarity').textContent=score===null?'Naive text similarity: omitted for long text':`Naive text similarity: ${(100*score).toFixed(1)}%`;}
function sourceKey(){return JSON.stringify({text:source.value,context,advisory:'demo-advisory',revision:1});}
function stale(message='Inputs changed. Verify again before relying on the previous result.'){
  generation++;receipt=null;$('receiptBtn').disabled=true;
  const r=$('result');r.className='result review';$('decision').textContent='STALE';$('summary').textContent=message;$('diffs').innerHTML='';$('technicalBody').innerHTML='';
  updateSimilarity();
}
function invalidateAuthority(){frozen={sourceKey:null,contract:null,token:null};$('sourceState').className='source-state';$('sourceState').textContent='Source changed; readiness must be checked again.';stale();}
function renderContext(){
  if(!context){$('contextCard').innerHTML='<div class="context-empty">No environmental context loaded.</div>';return;}
  const indicators=(context.indicators||[]).slice(0,6).join(', ')||'—';
  $('contextCard').innerHTML=`<div class="context-meta"><div class="meta-item"><small>Source</small><strong>${esc(context.source)}</strong></div><div class="meta-item"><small>Site</small><strong>${esc(context.site||'Not provided')}</strong></div><div class="meta-item"><small>Indicators</small><strong>${esc(indicators)}</strong></div><div class="meta-item"><small>Data state</small><strong>${context.synthetic_demo?'SYNTHETIC DEMO':'IMPORTED'}</strong></div></div><p class="micro hash">SHA-256 ${esc(context.dataset_sha256)}</p>`;
}
async function jsonFetch(url,options={}){const r=await fetch(url,options);const raw=await r.text();let body={};if(raw){try{body=JSON.parse(raw);}catch{if(!r.ok)throw new Error(`HTTP ${r.status}: ${raw.slice(0,500)}`);throw new Error(`HTTP ${r.status}: server returned non-JSON data`);}}if(!r.ok){const detail=body.detail;let message;if(typeof detail==='string'){message=detail;}else if(detail&&Array.isArray(detail.reasons)){message=detail.reasons.join(' ');}else if(detail&&Array.isArray(detail.errors)){message=detail.errors.join(' ');}else{message=JSON.stringify(detail)||`HTTP ${r.status}`;}throw new Error(message);}return body;}
async function loadDemoContext(){const myContextGen=++contextGeneration;const b=await jsonFetch('/api/aqua/demo-context');if(myContextGen!==contextGeneration)return;context=b.context;contextToken=b.context_token;renderContext();invalidateAuthority();}
async function importCsv(){const file=$('csvFile').files[0];if(!file){alert('Choose a CSV file first.');return;}if(file.size>2000000){alert('CSV context exceeds the 2 MB prototype limit.');return;}const myContextGen=++contextGeneration;try{const bytes=await file.arrayBuffer();const csv=new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes);if(myContextGen!==contextGeneration)return;const b=await jsonFetch('/api/aqua/context/resilience-csv',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csv_text:csv,synthetic_demo:false})});if(myContextGen!==contextGeneration)return;context=b.context;contextToken=b.context_token;renderContext();invalidateAuthority();}catch(e){if(myContextGen===contextGeneration)alert(e.message||'CSV context import failed.');}}
async function importFhir(){const raw=$('fhirInput').value;if(new TextEncoder().encode(raw).length>1000000){alert('FHIR context exceeds the 1 MB prototype limit.');return;}const myContextGen=++contextGeneration;try{const b=await jsonFetch('/api/aqua/context/fhir-raw',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({json_text:raw,synthetic_demo:false})});if(myContextGen!==contextGeneration)return;context=b.context;contextToken=b.context_token;renderContext();invalidateAuthority();}catch(e){if(myContextGen===contextGeneration)alert(e.message||'FHIR context import failed.');}}
async function freezeSource(){
  if(!context||!contextToken) throw new Error('Load environmental context before freezing the advisory.');
  const key=sourceKey();if(frozen.sourceKey===key&&frozen.contract&&frozen.token)return frozen;
  try{
    const b=await jsonFetch('/api/aqua/authority',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_text:source.value,context,context_token:contextToken,advisory_id:'demo-advisory',revision:1})});
    if(key!==sourceKey()) throw new Error('Source/context changed during readiness checking.');
    frozen={sourceKey:key,contract:b.source_contract,token:b.authority_token};
    $('sourceState').className='source-state ready';$('sourceState').textContent=`SOURCE READY · ${b.context_alignment} context alignment · ${b.semantic_profile}`;
    return frozen;
  }catch(e){if(key===sourceKey()){$('sourceState').className='source-state review';$('sourceState').textContent='SOURCE REVIEW · '+e.message;}throw e;}
}
function prettyDimension(field){const map={required_action:'ACTION',prohibited_action:'ACTION',candidate_only_required_action:'NEW ACTION',candidate_only_prohibited_action:'NEW ACTION',affected_area:'PLACE',candidate_only_affected_area:'PLACE',place_relation:'PLACE',place_identifier:'PLACE',time_precision:'TIME',constraint_force:'CONSTRAINT',audience:'AUDIENCE',candidate_only_audience:'AUDIENCE',quantity:'QUANTITY',candidate_only_quantity:'NEW QUANTITY',source_extraction_uncertainty:'SOURCE COVERAGE',candidate_extraction_uncertainty:'CANDIDATE COVERAGE'};if(field.includes('action'))return map[field]||'ACTION';return map[field]||field.replaceAll('_',' ').toUpperCase();}
function renderResult(b){
  const r=$('result'),decision=b.decision;r.className='result '+decision.toLowerCase();$('decision').textContent=b.display_decision||decision;$('summary').textContent=b.summary;$('methodBadge').textContent=b.verification_method||'Deterministic V1';
  const important=(b.signals||[]).filter(x=>x.status==='FAIL'||x.status==='UNKNOWN');
  $('diffs').innerHTML=important.length?important.slice(0,8).map(s=>`<div class="diff ${s.status==='FAIL'?'fail':'unknown'}"><strong>${esc(prettyDimension(s.field))}</strong><div class="diff-values"><div><span>Expected</span>${esc(s.expected||'—')}</div><div><span>Observed</span>${esc(s.observed||'—')}</div></div><p class="micro">${esc(s.reason)}</p></div>`).join(''):'<div class="diff"><strong>SUPPORTED PROFILE</strong><p>No critical differences were found across represented invariants.</p></div>';
  $('technicalBody').innerHTML=`<div class="signal-list">${(b.signals||[]).map(s=>`<div class="signal"><b>${esc(s.field)}</b> ${esc(s.status)} · ${esc(s.detector)}<br><span class="micro">${esc(s.reason)}</span></div>`).join('')}</div>`;
  receipt=b.integrity_receipt;$('receiptBtn').disabled=!receipt;
}
async function verify(){
  const myGen=++generation;const btn=$('verifyBtn');btn.disabled=true;btn.textContent='Verifying…';
  try{const auth=await freezeSource();const snapshot=sourceKey()+candidate.value;const b=await jsonFetch('/api/aqua/verify',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_text:source.value,source_contract:auth.contract,authority_token:auth.token,context,advisory_id:'demo-advisory',revision:1,candidate_text:candidate.value})});if(myGen!==generation||snapshot!==sourceKey()+candidate.value)return;renderResult(b);}catch(e){if(myGen===generation){const r=$('result');r.className='result review';$('decision').textContent='REVIEW';$('summary').textContent=e.message;$('diffs').innerHTML='';}}finally{btn.disabled=false;btn.textContent='Verify protective meaning';updateSimilarity();}
}
async function runBenchmark(){const b=await jsonFetch('/api/aqua/dev-benchmark');$('metrics').innerHTML=`<div><strong>${b.unsafe_pass}</strong><span>Unsafe PASS</span></div><div><strong>${b.unsafe_block}/${b.unsafe_total}</strong><span>Unsafe BLOCK</span></div><div><strong>${b.clean_pass}/${b.clean_total}</strong><span>Clean PASS</span></div><div><strong>${b.total}</strong><span>DEV cases</span></div>`;}

async function loadReleaseEvidence(){
  try{
    const b=await jsonFetch('/api/aqua/release-evidence');const m=b.metrics||{};
    $('holdoutMetrics').innerHTML=`<div><strong>${m.unsafe_pass}</strong><span>Unsafe PASS</span></div><div><strong>${m.unsafe_block}/${m.unsafe_total}</strong><span>Unsafe BLOCK</span></div><div><strong>${m.clean_pass}/${m.clean_total}</strong><span>Clean PASS</span></div><div><strong>${b.verified?'VERIFIED':'STALE'}</strong><span>Evidence status</span></div>`;
    $('holdoutHash').textContent=`Dataset SHA-256 ${b.dataset_sha256} · semantic ${b.semantic_fingerprint.slice(0,16)}…`;
  }catch(e){$('holdoutMetrics').innerHTML='<div><strong>STALE</strong><span>Release evidence</span></div>';$('holdoutHash').textContent=e.message;}
}

function downloadReceipt(){if(!receipt)return;const blob=new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'});const a=document.createElement('a');const url=URL.createObjectURL(blob);a.href=url;a.download=`${receipt.verification_id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),0);}

source.addEventListener('input',invalidateAuthority);candidate.addEventListener('input',()=>stale());$('demoContextBtn').addEventListener('click',loadDemoContext);$('csvImportBtn').addEventListener('click',importCsv);$('fhirImportBtn').addEventListener('click',importFhir);$('verifyBtn').addEventListener('click',verify);$('benchmarkBtn').addEventListener('click',runBenchmark);$('receiptBtn').addEventListener('click',downloadReceipt);
document.querySelectorAll('[data-demo]').forEach(btn=>btn.addEventListener('click',()=>{const d=DEMOS[btn.dataset.demo];source.value=d.source;candidate.value=d.candidate;invalidateAuthority();}));
updateSimilarity();loadDemoContext().catch(e=>{$('contextCard').innerHTML=`<div class="context-empty">${esc(e.message)}</div>`;});loadReleaseEvidence();
