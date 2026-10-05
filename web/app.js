'use strict';
const source=document.getElementById('source'),candidate=document.getElementById('candidate');
const SAFE=source.value;
const DISPLAY_DECISION={PASS:'PRESERVED',REVIEW:'REVIEW',BLOCK:'CRITICAL DRIFT'};
let frozenSource={key:null,contract:null,authorityToken:null};
let verifyGeneration=0;
let liveSessionReady=false;

function markVerificationStale(){
  verifyGeneration++;
  const status=document.getElementById('status'),signals=document.getElementById('signals');
  status.className='status review';
  status.innerHTML='<div class="status-dot"></div><div><div class="status-title">STALE</div><div class="status-copy">Candidate or authority changed. Reverify before relying on the previous result.</div></div>';
  signals.innerHTML='';
}
async function ensureLiveSession(provider){
  if(provider!=='openai' || liveSessionReady) return;
  const token=window.prompt('Enter the SignalLock live-demo token for this browser session.');
  if(!token) throw new Error('Live demo authentication cancelled.');
  const r=await fetch('/api/live-session',{method:'POST',headers:{'X-SignalLock-Demo-Token':token}});
  const body=await r.json();
  if(!r.ok) throw new Error(body.detail||'Live demo authentication failed');
  liveSessionReady=true;
}
function setSafe(){candidate.value=SAFE.replace('shelter indoors','stay indoors');document.getElementById('candidateLang').value='en';markVerificationStale();}
function setFault(){candidate.value=SAFE.replace('Do not enter','Enter');document.getElementById('candidateLang').value='en';markVerificationStale();}
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));}
function summarizeContract(c){
  const req=(c.required_actions||[]).map(x=>esc(`${x.type}: ${x.verb}${x.destination?' → '+x.destination:''}${x.deadline?' · '+(x.temporal_operator?x.temporal_operator+' ':'')+x.deadline:''}`)).join('<br>')||'—';
  const pro=(c.prohibited_actions||[]).map(x=>esc(`${x.verb} ${x.object||''}`)).join('<br>')||'—';
  const qty=(c.quantities||[]).map(x=>esc(`${x.value} ${x.unit}${x.meaning?' · '+x.meaning:''}`)).join(', ')||'—';
  return `<dt>Required action</dt><dd>${req}</dd><dt>Prohibited</dt><dd>${pro}</dd><dt>Areas</dt><dd>${esc((c.affected_areas||[]).join(', ')||'—')}</dd><dt>Quantities</dt><dd>${qty}</dd><dt>Audience</dt><dd>${esc((c.audience||[]).join(', ')||'—')}</dd>`;
}
function sourceKey(){return JSON.stringify({text:source.value,provider:document.getElementById('provider').value,language:'en'});}
function invalidateSourceContract(){frozenSource={key:null,contract:null,authorityToken:null};markVerificationStale();}
function verificationSnapshot(){return JSON.stringify({sourceKey:sourceKey(),candidate:candidate.value,candidateLanguage:document.getElementById('candidateLang').value,provider:document.getElementById('provider').value});}
function snapshotStillCurrent(snapshot,generation){return generation===verifyGeneration && snapshot===verificationSnapshot();}
async function getFrozenSourceContract(){
  const key=sourceKey();
  if(frozenSource.key===key && frozenSource.contract && frozenSource.authorityToken) return frozenSource;
  const provider=document.getElementById('provider').value;
  const r=await fetch('/api/extract-authority',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:source.value,language:'en',provider,source_id:'authoritative-source'})});
  const body=await r.json();
  if(!r.ok) throw new Error(body.detail||'Authoritative source extraction failed');
  if(key!==sourceKey()) throw new Error('Authoritative source changed while it was being extracted; retry verification.');
  frozenSource={key,contract:body.source_contract,authorityToken:body.authority_token};
  return frozenSource;
}
async function verify(){
 const generation=++verifyGeneration;
 const snapshot=verificationSnapshot();
 const btn=document.getElementById('verifyBtn'); btn.classList.add('busy'); btn.textContent='Verifying…';
 const status=document.getElementById('status'),signals=document.getElementById('signals'); signals.innerHTML='';
 try{
   const provider=document.getElementById('provider').value;
   await ensureLiveSession(provider);
   const authority=await getFrozenSourceContract();
   const sourceContract=authority.contract;
   if(!snapshotStillCurrent(snapshot,generation)) return;
   const r=await fetch('/api/verify-contract',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_text:source.value,source_contract:sourceContract,authority_token:authority.authorityToken,candidate_text:candidate.value,candidate_language:document.getElementById('candidateLang').value,provider})});
   const body=await r.json(); if(!r.ok) throw new Error(body.detail||'Verification failed');
   if(!snapshotStillCurrent(snapshot,generation)) return;
   status.className='status '+body.decision.toLowerCase();
   status.innerHTML=`<div class="status-dot"></div><div><div class="status-title">${esc(DISPLAY_DECISION[body.decision]||body.decision)}</div><div class="status-copy">${esc(body.summary)}</div></div>`;
   document.getElementById('contract').innerHTML=summarizeContract(body.source_contract);
   signals.innerHTML=(body.signals||[]).map(s=>`<div class="signal"><b>${esc(s.field)}</b><span class="pill ${esc(s.status)}">${esc(s.status)}</span><div>${esc(s.reason)}<br><span class="signal-detail">expected: ${esc(s.expected||'—')} · observed: ${esc(s.observed||'—')}</span></div></div>`).join('');
 }catch(e){if(snapshotStillCurrent(snapshot,generation)){status.className='status review';status.innerHTML=`<div class="status-dot"></div><div><div class="status-title">REVIEW</div><div class="status-copy">${esc(e.message)}</div></div>`;}}
 finally{if(generation===verifyGeneration){btn.classList.remove('busy');btn.textContent='Check alert integrity';}}
}
async function generateTransform(mode){
 const provider=document.getElementById('provider').value;
 const lang=document.getElementById('candidateLang').value;
 await ensureLiveSession(provider);
 if(mode==='translate' && provider==='heuristic'){alert('Select Live multilingual AI for translation. The offline demo intentionally refuses to fake translation.');return;}
 const payload={text:source.value,mode,provider,max_chars:360,source_language:'en'};
 if(mode==='translate') payload.language=lang;
 const sourceSnapshot=sourceKey();
 try{
  await getFrozenSourceContract();
  if(sourceSnapshot!==sourceKey()) return;
  const r=await fetch('/api/transform',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const b=await r.json(); if(!r.ok) throw new Error(b.detail||'Transform failed');
  if(sourceSnapshot!==sourceKey()) return;
  candidate.value=b.text;
  document.getElementById('candidateLang').value=b.metadata.output_language||'en';
  markVerificationStale();
  await verify();
 }catch(e){alert(e.message);}
}
async function loadBenchmark(){
 const r=await fetch('/api/benchmark');const b=await r.json();const m=b.metrics,p=x=>`${(100*x).toFixed(1)}%`;
 document.getElementById('metrics').innerHTML=`<div class="metric"><strong>${p(m.critical_unsafe_pass_rate)}</strong><span>Unsafe PASS rate ↓</span></div><div class="metric"><strong>${p(m.unsafe_block_rate)}</strong><span>Unsafe BLOCK recall ↑</span></div><div class="metric"><strong>${p(m.clean_pass_rate)}</strong><span>Clean PASS rate ↑</span></div><div class="metric"><strong>${m.total}</strong><span>Controlled cases</span></div>`;
 document.getElementById('faults').innerHTML=Object.entries(m.per_fault).map(([k,v])=>`<div class="fault"><b>${esc(k)}</b><div>${v.caught}/${v.total} intercepted · ${(100*v.catch_rate).toFixed(0)}%</div></div>`).join('');
}

source.addEventListener('input',invalidateSourceContract);
candidate.addEventListener('input',markVerificationStale);
document.getElementById('candidateLang').addEventListener('change',markVerificationStale);
document.getElementById('provider').addEventListener('change',invalidateSourceContract);
document.getElementById('provider').addEventListener('change',()=>{liveSessionReady=false;});
document.getElementById('safeBtn').addEventListener('click',setSafe);
document.getElementById('faultBtn').addEventListener('click',setFault);
document.getElementById('simplifyBtn').addEventListener('click',()=>generateTransform('simplify'));
document.getElementById('smsBtn').addEventListener('click',()=>generateTransform('sms'));
document.getElementById('translateBtn').addEventListener('click',()=>generateTransform('translate'));
document.getElementById('verifyBtn').addEventListener('click',verify);
document.getElementById('benchmarkBtn').addEventListener('click',loadBenchmark);
verify();loadBenchmark();
