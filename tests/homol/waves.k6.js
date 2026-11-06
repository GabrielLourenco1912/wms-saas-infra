import http from 'k6/http';
import {check,sleep} from 'k6';
import execution from 'k6/execution';
import {Trend} from 'k6/metrics';

const plan=JSON.parse(open('/private/benchmark-plan.json'));
const mode=__ENV.MODE || 'baseline';
const receipts=new Trend('receipt_confirmation_ms',true);
const waves=new Trend('wave_generation_ms',true);
const thresholds={checks:['rate==1'],http_req_failed:['rate==0'],receipt_confirmation_ms:[`p(95)<${plan.protocol.operationalHttpP95LimitMs}`]};
if(mode==='concurrent') {
  thresholds.wave_generation_ms=[`p(95)<${plan.protocol.waveP95LimitMs}`];
  for(const size of plan.protocol.waveOrderCounts)thresholds[`wave_generation_ms{orders:${size}}`]=[`p(95)<${plan.protocol.waveP95LimitMs}`];
}
export const options={
  scenarios:{
    operations:{executor:'per-vu-iterations',exec:'confirmReceipt',vus:2,iterations:plan.protocol.operationalIterationsPerPhase/2,maxDuration:'3m'},
    ...(mode==='concurrent'?{waves:{executor:'shared-iterations',exec:'generateWave',vus:1,iterations:plan.waves.length,maxDuration:'3m'}}:{}),
  },
  thresholds,
  summaryTrendStats:['min','med','p(95)','max','avg'],
};
export function confirmReceipt() {
  const row=plan.receipts[mode][execution.scenario.iterationInTest];
  const token=plan.operatorTokens[execution.vu.idInTest%2];
  const response=http.post(`${plan.apiBase}/api/receipts/${row.id}/confirm`,JSON.stringify(row.body),{
    headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json','Idempotency-Key':row.key},
    tags:{name:'POST /api/receipts/:id/confirm',phase:mode},timeout:'30s',
  });
  receipts.add(response.timings.duration,{phase:mode});
  check(response,{'receipt commits exactly one new confirmation':r=>(r.status===200||r.status===201)&&Boolean(r.json('data.confirmation.id'))});
  sleep(1);
}
export function generateWave() {
  const row=plan.waves[execution.scenario.iterationInTest];
  const response=http.post(`${plan.apiBase}/api/waves`,JSON.stringify(row.body),{
    headers:{Authorization:`Bearer ${plan.managerToken}`,'Content-Type':'application/json'},
    tags:{name:'POST /api/waves',orders:String(row.size),phase:mode},timeout:'30s',
  });
  waves.add(response.timings.duration,{orders:String(row.size)});
  check(response,{'wave reserves every requested item':r=>r.status===201&&r.json('data.tasks').length===row.size});
}
export function handleSummary(data) {
  return {[`/artifacts/benchmark-${mode}-summary.json`]:JSON.stringify(data,null,2),stdout:`Benchmark ${mode}: ${JSON.stringify({receipts:data.metrics.receipt_confirmation_ms?.values,waves:data.metrics.wave_generation_ms?.values,checks:data.metrics.checks?.values})}\n`};
}
