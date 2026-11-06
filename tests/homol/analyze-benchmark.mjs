import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {api,fixture,login,output,pageAll,save} from './support.mjs';

const summaries={};
const rows=[];
for(const phase of ['baseline','concurrent']) {
  const summary=JSON.parse(fs.readFileSync(path.join(output,`benchmark-${phase}-summary.json`),'utf8'));
  summaries[phase]=summary.metrics;
  for(const line of fs.readFileSync(path.join(output,`benchmark-${phase}-samples.json`),'utf8').trim().split('\n')) {
    const value=JSON.parse(line);
    if(value.type==='Point'&&['wave_generation_ms','receipt_confirmation_ms'].includes(value.metric)) {
      rows.push({phase,metric:value.metric,orders:value.data.tags.orders||'',time:value.data.time,durationMs:value.data.value});
    }
  }
}
const manager=await login('manager');
const stock=await api('/stock/'+fixture.loadStock,{token:manager});
assert(Number(stock.reservedQuantity)<=Number(stock.quantity));
const orders=await pageAll(manager,'orders',{warehouseId:fixture.warehouse});
let checked=0;
for(const order of orders.filter(row=>row.documentNumber?.startsWith('LOAD-'))) {
  const detail=Array.isArray(order.items)?order:await api('/orders/'+order.id,{token:manager});
  for(const item of detail.items)assert(Number(item.reservedQuantity)+Number(item.pickedQuantity)+Number(item.fulfilledQuantity)<=Number(item.requestedQuantity));
  checked++;
}
save('benchmark-results.json',{measuredAt:new Date().toISOString(),summaries,sampleCounts:{waves:rows.filter(row=>row.metric==='wave_generation_ms').length,receipts:rows.filter(row=>row.metric==='receipt_confirmation_ms').length},demandConsistencyCheckedOrders:checked,reservedQuantity:Number(stock.reservedQuantity),physicalQuantity:Number(stock.quantity)});
fs.writeFileSync(path.join(output,'benchmark-samples.csv'),'phase,metric,orders,time,duration_ms\n'+rows.map(row=>[row.phase,row.metric,row.orders,row.time,row.durationMs].join(',')).join('\n')+'\n');
console.log('Resultados e amostras de desempenho exportados; reservas e demanda verificadas.');
