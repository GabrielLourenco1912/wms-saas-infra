import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {createRequire} from 'node:module';
import {api, command, credentials, fixture, key, login, measurements, otp, output, pageAll, root, runId, save, webBase} from './support.mjs';

const require=createRequire(path.join(root,'wms-saas-web/package.json'));
const {chromium}=require('playwright');
let manager=await login('manager');
const warehouse=await api('/warehouses/'+fixture.warehouse,{token:manager});
assert(warehouse.name.includes('HOMOLOGAÇÃO'), 'A base precisa conter o marcador de homologação');
const product=await api('/products',{method:'POST',token:manager,body:{categoryId:fixture.category,sku:`E2E-${runId}`,name:`Produto E2E ${runId}`,lotControlled:false,expiryControlled:false,shelfLifeDays:null,active:true,baseUnit:'UN',unitWeightKg:0.1,unitVolumeM3:0.001}});
const pack=await api(`/products/${product.id}/packages`,{method:'POST',token:manager,body:{type:'UNIDADE',conversionFactor:1,barcode:`E2E-${runId}`,weightKg:0.1,volumeM3:0.001,active:true}});
const browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})});
const context=await browser.newContext({viewport:{width:1440,height:1000}});
const page=await context.newPage();
page.setDefaultTimeout(20000);
const results=[];
async function screenshot(name) { await page.screenshot({path:path.join(output,name+'.png'),fullPage:true}); }
async function scenario(name, work) {
  const started=Date.now();
  try {const data=await work();results.push({name,status:'passed',durationMs:Date.now()-started});save('acceptance-results.json',results);return data;}
  catch(error){results.push({name,status:'failed',message:String(error.message),durationMs:Date.now()-started});save('acceptance-results.json',results);await screenshot('failure').catch(()=>{});throw error;}
}
async function lookup(scope,label,query) {
  await scope.getByRole('button',{name:new RegExp('^'+label+' ')}).first().click();
  await scope.getByRole('searchbox',{name:'Pesquisar '+label,exact:true}).fill(query);
  const choices=scope.getByRole('list',{name:'Opções de '+label});
  await choices.getByRole('button').filter({hasText:query}).first().click();
}
await scenario('C01: login do gestor pelo painel, código SMTP e cookie HttpOnly reais',async()=>{
  await page.goto(webBase+'/auth/login');
  await page.getByLabel('E-mail',{exact:true}).fill(credentials.managerEmail);
  await page.getByLabel('Senha',{exact:true}).fill(credentials.managerPassword);
  const after=Date.now()-1000;
  await page.getByRole('button',{name:'Continuar',exact:true}).click();
  await page.getByLabel('Código de verificação').waitFor();
  await page.getByLabel('Código de verificação').fill(await otp(credentials.managerEmail,after));
  await page.getByRole('button',{name:'Confirmar e entrar'}).click();
  await page.getByRole('heading',{name:'Visão geral',exact:true}).waitFor();
  assert((await context.cookies()).some(cookie=>cookie.name==='refresh_token'&&cookie.httpOnly));
  await screenshot('01-web-dashboard');
});

const state={runId,fixture,product,pack,receiptDocument:`E2E-IN-${runId}`,orderDocument:`E2E-OUT-${runId}`,inboundLpn:`E2E-IN-LPN-${runId}`,outboundLpn:`E2E-OUT-LPN-${runId}`};
await scenario('C03: pré-recebimento criado pela interface sem criação de saldo',async()=>{
  await page.goto(webBase+'/gestao/receipts');
  await page.getByRole('button',{name:'Novo pré-recebimento',exact:true}).click();
  const dialog=page.getByRole('dialog');
  await lookup(dialog,'Armazém','HOMOLOGAÇÃO');
  await lookup(dialog,'Fornecedor','Fornecedor sintético');
  await dialog.getByLabel('Número do documento',{exact:false}).fill(state.receiptDocument);
  await lookup(dialog,'Produto 1',product.sku);
  await dialog.getByLabel('Quantidade do item 1',{exact:true}).fill('20');
  await dialog.getByRole('button',{name:'Criar pré-recebimento',exact:true}).click();
  await dialog.waitFor({state:'detached'});
  const receipts=await pageAll(manager,'pre-receipts',{q:state.receiptDocument});
  assert.equal(receipts.length,1);state.receipt=await api('/receipts/'+receipts[0].id,{token:manager});
  assert.equal((await pageAll(manager,'stock',{productId:product.id})).length,0);
  await screenshot('02-web-pre-receipt');
});
save('scenario.json',state);

async function prepareWave() {
  manager=await login('manager');
  await scenario('C04: conferência e putaway feitos pelo Flutter persistiram na base real',async()=>{
    const stocks=await pageAll(manager,'stock',{productId:product.id});
    assert.equal(stocks.reduce((sum,row)=>sum+Number(row.quantity),0),20);
    assert(stocks.every(row=>row.positionCode.startsWith('H-A')));
    state.stocks=stocks;
  });
  await scenario('C05: pedido de saída criado pelo painel',async()=>{
    await page.goto(webBase+'/gestao/orders');
    await page.getByRole('button',{name:'Novo pedido',exact:true}).click();
    const dialog=page.getByRole('dialog');
    await lookup(dialog,'Armazém','HOMOLOGAÇÃO');
    await lookup(dialog,'Cliente','Cliente sintético');
    await dialog.getByLabel('Número do documento',{exact:false}).fill(state.orderDocument);
    await lookup(dialog,'Produto 1',product.sku);
    await dialog.getByLabel('Quantidade do item 1',{exact:true}).fill('8');
    await dialog.getByRole('button',{name:'Criar pedido',exact:true}).click();
    await dialog.waitFor({state:'detached'});
    state.order=(await pageAll(manager,'orders',{q:state.orderDocument})).find(row=>row.documentNumber===state.orderDocument);
    assert(state.order);
  });
  await scenario('C05: onda criada pelo painel reserva o saldo e gera tarefa real',async()=>{
    await page.getByRole('tab',{name:'Ondas',exact:true}).click();
    await page.getByRole('button',{name:'Nova onda',exact:true}).click();
    const dialog=page.getByRole('dialog');
    await lookup(dialog,'Armazém','HOMOLOGAÇÃO');
    await dialog.getByLabel('Código da onda',{exact:true}).fill('E2E-WAVE-'+runId);
    await lookup(dialog,'Pesquisar pedido',state.orderDocument);
    await dialog.getByRole('button',{name:'Adicionar pedido',exact:true}).click();
    const response=page.waitForResponse(r=>r.url().endsWith('/waves')&&r.request().method()==='POST');
    await dialog.getByRole('button',{name:'Gerar onda e reservar',exact:true}).click();
    const result=await response;assert.equal(result.status(),201);
    state.wave=(await result.json()).data;
    await dialog.waitFor({state:'detached'});
    assert.equal(state.wave.tasks.length,1);
    assert.equal(Number(state.wave.tasks[0].targetQuantity),8);
    await screenshot('03-web-orders-wave');
  });
  return state;
}

async function afterPicking() {
  manager=await login('manager');
  await scenario('C06: picking transfere internamente sem efetuar baixa externa',async()=>{
    const order=await api('/orders/'+state.order.id,{token:manager});
    assert.equal(Number(order.items[0].pickedQuantity),8);
    assert.equal(Number(order.items[0].fulfilledQuantity),0);
    const stocks=await pageAll(manager,'stock',{productId:product.id});
    assert.equal(stocks.reduce((sum,row)=>sum+Number(row.quantity),0),20);
  });
  return state;
}
async function afterShipment() {
  state.shipment=(await pageAll(manager,'shipments',{orderId:state.order.id})).find(row=>row.orderId===state.order.id);
  assert(state.shipment,'Carga criada no Flutter deve existir na API');
  return state;
}
async function finish() {
  manager=await login('manager');
  await scenario('C07: despacho Flutter dá baixa única e atende integralmente o pedido',async()=>{
    const order=await api('/orders/'+state.order.id,{token:manager});
    assert.equal(order.status,'ATENDIDO');assert.equal(Number(order.items[0].fulfilledQuantity),8);
    const stocks=await pageAll(manager,'stock',{productId:product.id});
    assert.equal(stocks.reduce((sum,row)=>sum+Number(row.quantity),0),12);
    const ledger=await pageAll(manager,'stock-transactions',{productId:product.id});
    assert.equal(ledger.filter(row=>row.movementType==='SAIDA'||row.type==='SAIDA').length,1);
    save('cycle-ledger.json',ledger);save('cycle-final-stock.json',stocks);
    await page.goto(webBase+'/gestao/stock');
    await page.getByRole('searchbox',{name:'Pesquisar por SKU, produto, LPN, posição ou lote'}).fill(product.sku);
    await page.getByText(product.sku,{exact:false}).first().waitFor();
    await screenshot('04-web-final-stock');
  });
  const {runApiScenarios}=await import('./api-scenarios.mjs');
  await runApiScenarios({manager,scenario,state});
  save('http-measurements.json',measurements);
  save('scenario.json',state);
  return {passed:results.filter(row=>row.status==='passed').length};
}

const phases=new Map();
const server=http.createServer(async(req,res)=>{
  if(req.headers.authorization!==`Bearer ${credentials.driverToken}`){res.writeHead(403);res.end();return;}
  try {
    const route=new URL(req.url,'http://localhost').pathname;
    let data;
    if(route==='/config')data={...state,operatorEmail:credentials.operatorEmail,operatorPassword:credentials.operatorPassword};
    else if(route==='/otp')data={code:await otp(credentials.operatorEmail)};
    else {
      const actions={'/phase/received':async()=>{state.putaway=(await pageAll(manager,'putaway-tasks',{orderId:state.receipt.receipt.id})).find(row=>row.lpnCode===state.inboundLpn);assert(state.putaway);return state;},'/phase/putaway':prepareWave,'/phase/picked':afterPicking,'/phase/shipment':afterShipment,'/phase/finish':finish};
      const action=actions[route];assert(action,'Rota de teste inválida');
      if(!phases.has(route))phases.set(route,action());
      data=await phases.get(route);
    }
    res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(data));
  } catch(error){console.error(error.message);res.writeHead(500,{'Content-Type':'application/json'});res.end(JSON.stringify({error:error.message}));}
});
server.listen(Number(process.env.HOMOL_DRIVER_PORT||8777),'127.0.0.1',()=>console.log('Driver de aceitação pronto; credenciais omitidas.'));
async function close(){server.close();await browser.close();process.exit();}
process.on('SIGTERM',close);process.on('SIGINT',close);
