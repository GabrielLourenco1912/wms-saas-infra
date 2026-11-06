import assert from 'node:assert/strict';
import {api,command,fixture,key,login,pageAll,runId,save} from './support.mjs';

export async function runApiScenarios({manager,scenario,state}) {
  const operator=await login('operator');
  const orderFor=async(productId,quantity=5)=>api('/orders',{method:'POST',token:manager,body:{warehouseId:fixture.warehouse,partnerId:fixture.customer,documentNumber:`CHECK-${runId}-${key().slice(0,5)}`,items:[{productId,quantity}]}});
  const waveFor=async(order)=>command(manager,'/waves',{warehouseId:fixture.warehouse,code:`CHECK-${runId}-${key().slice(0,6)}`,orderIds:[order.id],priority:0},true);
  const cancelWave=async(wave)=>command(manager,`/waves/${wave.id}/cancel`,{reason:'Encerramento de cenário sintético'},true);

  await scenario('C01: operador recebe 403 ao tentar administrar usuários',async()=>{
    await api('/users',{token:operator,expected:[403]});
  });
  await scenario('C05: FEFO escolhe validade 2029 antes de 2030; cancelamento libera a reserva',async()=>{
    const order=await orderFor(fixture.traceProduct);
    const wave=await waveFor(order);
    assert.equal(wave.tasks[0].sourceStockId,fixture.traceStock2029);
    await cancelWave(wave);
    const stock=await api('/stock/'+fixture.traceStock2029,{token:manager});
    assert.equal(Number(stock.reservedQuantity),0);
  });
  await scenario('C05: FIFO escolhe a camada mais antiga quando não há validade',async()=>{
    const order=await orderFor(fixture.fifoProduct);
    const wave=await waveFor(order);
    assert.equal(wave.tasks[0].sourceStockId,fixture.fifoStockOld);
    await cancelWave(wave);
  });
  await scenario('C06: falta física zero bloqueia o saldo e realoca em outra posição',async()=>{
    const order=await orderFor(fixture.traceProduct);
    const wave=await waveFor(order);
    const task=wave.tasks[0];
    await command(operator,`/picking-tasks/${task.id}/start`,{},true);
    const result=await command(operator,`/picking-tasks/${task.id}/divergences`,{actualQuantity:0,sourceLpnCode:task.sourceLpnCode,sourcePositionCode:task.originPositionCode,productCode:'HOMOL-TRACE',reason:'Falta física sintética'},true);
    assert.equal(result.task.status,'DIVERGENTE');assert(result.replacementTasks.length>0);
    assert(result.replacementTasks.every(row=>row.originPositionId!==task.originPositionId));
    await cancelWave(wave);
    await command(manager,`/stock/${task.sourceStockId}/unblock`,{reason:'Cenário de falta encerrado'});
  });
  await scenario('C08: bloqueio por lote exclui o saldo da alocação até a liberação',async()=>{
    const block=await command(manager,'/stock-blocks/lots',{warehouseId:fixture.warehouse,productId:fixture.traceProduct,lot:'LOTE-2029',reason:'Bloqueio sintético'});
    const order=await orderFor(fixture.traceProduct);
    const wave=await waveFor(order);
    assert(wave.tasks.every(row=>row.sourceStockId!==fixture.traceStock2029));
    await cancelWave(wave);
    await command(manager,`/stock-blocks/${block.id}/release`,{reason:'Liberação sintética'});
  });

  const position=await api('/positions',{method:'POST',token:manager,body:{zoneId:fixture.zone,code:`I-${runId}`,type:'PISO',weightCapacityKg:10000,volumeCapacityM3:1000,purpose:'ARMAZENAGEM',active:true}});
  let moved;
  await scenario('C04: transferência parcial rejeita código errado e preserva o total físico',async()=>{
    const stocks=await pageAll(manager,'stock',{productId:state.product.id});
    const source=stocks.find(row=>Number(row.quantity)>2);
    const task=await command(operator,'/transfers',{stockId:source.id,destinationPositionId:position.id,destinationLpnCode:`INV-${runId}`,quantity:2});
    const body={actualQuantity:2,scannedLpnCode:source.lpnCode,scannedOriginCode:source.positionCode,scannedDestinationCode:position.code,scannedProductCode:state.product.sku};
    await api(`/transfers/${task.id}/confirm`,{method:'POST',token:operator,headers:{'Idempotency-Key':key()},body:{...body,scannedOriginCode:'INCORRETO'},expected:[422]});
    const idempotency=key();
    const first=await api(`/transfers/${task.id}/confirm`,{method:'POST',token:operator,headers:{'Idempotency-Key':idempotency},body});
    const replay=await api(`/transfers/${task.id}/confirm`,{method:'POST',token:operator,headers:{'Idempotency-Key':idempotency},body});
    assert.equal(first.id,replay.id);
    const final=await pageAll(manager,'stock',{productId:state.product.id});
    assert.equal(final.reduce((sum,row)=>sum+Number(row.quantity),0),12);
    moved=final.find(row=>row.positionId===position.id);assert.equal(Number(moved.quantity),2);
  });
  for(const [label,counted,expectedDelta] of [['negativo',1,-1],['positivo',3,2],['zero',3,0]]) {
    await scenario(`C09: inventário com ajuste ${label} e posição congelada`,async()=>{
      const before=await pageAll(manager,'stock-transactions',{productId:state.product.id});
      const detail=await command(operator,'/inventories',{positionId:position.id,scannedPositionCode:position.code});
      const inventory=detail.inventory;
      const item=detail.items[0];assert(item);
      const delta=counted-Number(item.theoreticalQuantity);assert.equal(delta,expectedDelta);
      await api('/transfers',{method:'POST',token:operator,headers:{'Idempotency-Key':key()},body:{stockId:moved.id,destinationPositionId:fixture.storageA,destinationLpnCode:`FROZEN-${runId}`,quantity:1},expected:[422]});
      await command(operator,`/inventories/${inventory.id}/counts`,{scannedPositionCode:position.code,items:[{inventoryItemId:item.id,lpnCode:item.lpnCode,scannedProductCode:item.sku,countedQuantity:counted}]});
      await command(manager,`/inventories/${inventory.id}/adjust`,{scannedPositionCode:position.code,reason:`Ajuste ${label} sintético`});
      const after=await pageAll(manager,'stock-transactions',{productId:state.product.id});
      assert.equal(after.length-before.length,delta===0?0:1);
      const stock=await api('/stock/'+moved.id,{token:manager});assert.equal(Number(stock.quantity),counted);
    });
  }
  await scenario('C03: recebimento exige lote/validade e uma rejeição não cria saldo',async()=>{
    const receipt=await command(manager,'/pre-receipts',{warehouseId:fixture.warehouse,partnerId:fixture.supplier,documentNumber:`TRACE-${runId}`,items:[{productId:fixture.traceProduct,quantity:1}]});
    const before=await pageAll(manager,'stock',{productId:fixture.traceProduct});
    await api(`/receipts/${receipt.receipt.id}/confirm`,{method:'POST',token:operator,headers:{'Idempotency-Key':key()},body:{orderItemId:receipt.items[0].id,packagingId:fixture.tracePackaging,quantity:1,lpnCode:`MISSING-${runId}`,positionId:fixture.receivingDock,scannedProductCode:'HOMOL-TRACE',scannedLpnCode:`MISSING-${runId}`,scannedPositionCode:'H-REC'},expected:[422]});
    const after=await pageAll(manager,'stock',{productId:fixture.traceProduct});assert.equal(after.length,before.length);
  });
  await scenario('C08: cancelamento de pedido preserva tarefas e libera suas reservas',async()=>{
    const order=await orderFor(fixture.fifoProduct);
    const wave=await waveFor(order);
    await command(manager,`/orders/${order.id}/cancel`,{reason:'Cancelamento sintético'},true);
    for(const task of wave.tasks) {
      const current=await api('/picking-tasks/'+task.id,{token:manager});assert.equal(current.status,'CANCELADA');
    }
  });
  await scenario('C09: tentativas de escrita direta no livro razão são rejeitadas',async()=>{
    await api('/stock-transactions',{method:'POST',token:manager,body:{},expected:[403,405]});
  });
  save('supplementary-final-stock.json',await pageAll(manager,'stock',{productId:state.product.id}));
}
