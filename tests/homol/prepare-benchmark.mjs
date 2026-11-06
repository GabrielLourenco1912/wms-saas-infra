import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {api,apiBase,command,fixture,key,login,output,root,runId,save} from './support.mjs';

const protocolPath=path.join(root,'tests/homol/performance-protocol.json');
const protocol=JSON.parse(fs.readFileSync(protocolPath,'utf8'));
let manager=await login('manager');
const plan={apiBase,protocol,waves:[],receipts:{baseline:[],concurrent:[]}};
for(let repetition=0;repetition<protocol.repetitionsPerCount;repetition++) {
  for(const count of protocol.waveOrderCounts) {
    const orderIds=[];
    for(let index=0;index<count;index++) {
      const order=await api('/orders',{method:'POST',token:manager,body:{warehouseId:fixture.warehouse,partnerId:fixture.customer,documentNumber:`LOAD-${runId}-${repetition}-${count}-${index}`,items:[{productId:fixture.loadProduct,quantity:1}]}});
      orderIds.push(order.id);
    }
    plan.waves.push({size:count,body:{warehouseId:fixture.warehouse,code:`LOAD-${runId}-${repetition}-${count}`,orderIds,priority:0,idempotencyKey:key()}});
  }
}
for(const phase of ['baseline','concurrent']) {
  for(let index=0;index<protocol.operationalIterationsPerPhase;index++) {
    const receipt=await command(manager,'/pre-receipts',{warehouseId:fixture.warehouse,partnerId:fixture.supplier,documentNumber:`LAT-${runId}-${phase}-${index}`,items:[{productId:fixture.loadProduct,quantity:1}]});
    const lpn=`LAT-${runId}-${phase}-${index}`;
    plan.receipts[phase].push({id:receipt.receipt.id,key:key(),body:{orderItemId:receipt.items[0].id,packagingId:fixture.loadPackaging,quantity:1,lpnCode:lpn,positionId:fixture.receivingDock,scannedProductCode:'HOMOL-LOAD',scannedLpnCode:lpn,scannedPositionCode:'H-REC'}});
  }
}
// Obtain sessions after setup so authentication/setup time isn't measured as domain latency.
manager=await login('manager');
plan.managerToken=manager;
plan.operatorTokens=[await login('operator'),await login('concurrent')];
const destination=process.env.HOMOL_BENCHMARK_PLAN;
if(!destination)throw new Error('HOMOL_BENCHMARK_PLAN precisa apontar para arquivo privado');
fs.writeFileSync(destination,JSON.stringify(plan),{mode:0o600});
save('benchmark-workload.json',{runId,protocol,protocolSha256:crypto.createHash('sha256').update(fs.readFileSync(protocolPath)).digest('hex'),orders:plan.waves.reduce((sum,row)=>sum+row.size,0),waves:plan.waves.length,receiptsPerPhase:protocol.operationalIterationsPerPhase,preparedAt:new Date().toISOString()});
console.log(`Carga preparada: ${plan.waves.length} ondas; documentos novos e credenciais omitidas.`);
