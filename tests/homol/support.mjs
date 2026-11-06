import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {setTimeout as delay} from 'node:timers/promises';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const output = path.resolve(process.env.HOMOL_ARTIFACT_DIR || path.join(root, 'artifacts/homol/local'));
fs.mkdirSync(output, {recursive:true});
export const credentials = JSON.parse(fs.readFileSync(process.env.HOMOL_CREDENTIALS_FILE, 'utf8'));
export const fixture = JSON.parse(fs.readFileSync(path.join(root, 'wms-saas-backend/docs/HOMOLOGACAO_FIXTURES.json'), 'utf8'));
export const apiBase = (process.env.HOMOL_API_URL || 'http://127.0.0.1:8888').replace(/\/$/, '');
export const webBase = (process.env.HOMOL_WEB_URL || 'http://127.0.0.1:3333').replace(/\/$/, '');
export const mailBase = (process.env.HOMOL_MAILPIT_URL || 'http://127.0.0.1:8026').replace(/\/$/, '');
export const runId = process.env.HOMOL_RUN_ID || crypto.randomBytes(5).toString('hex');
assert(['127.0.0.1','localhost','homol.api.wms.lourencogabriel.dev'].includes(new URL(apiBase).hostname), 'A API precisa ser local ou do domínio explícito de homologação');
assert(['127.0.0.1','localhost','homol.wms.lourencogabriel.dev'].includes(new URL(webBase).hostname), 'O painel precisa ser local ou do domínio explícito de homologação');
export const key = () => crypto.randomUUID();
export const measurements = [];

export async function request(base, endpoint, {method='GET', token, body, headers={}, expected}={}) {
  const started = performance.now();
  const response = await fetch(base + endpoint, {
    method, headers:{Accept:'application/json', ...(body ? {'Content-Type':'application/json'} : {}),
      ...(token ? {Authorization:`Bearer ${token}`} : {}), ...headers},
    ...(body ? {body:JSON.stringify(body)} : {}), signal:AbortSignal.timeout(30000),
  });
  const text = await response.text();
  let parsed;
  try { parsed = JSON.parse(text); } catch { parsed = {message:'Resposta não JSON'}; }
  if (!endpoint.startsWith('/api/auth')) measurements.push({method, path:endpoint.split('?')[0], status:response.status, durationMs:performance.now()-started});
  const accepted = expected ? expected.includes(response.status) : response.ok;
  assert(accepted, `${method} ${endpoint.split('?')[0]}: HTTP ${response.status}; ${parsed.message || ''}`);
  return {status:response.status, data:parsed.data, raw:parsed};
}
export const api = (endpoint, options={}) => request(apiBase, '/api'+endpoint, options).then(result=>result.data);
export const command = (token, endpoint, body={}, inBody=false) => api(endpoint, {
  method:'POST',token,body:inBody ? {...body,idempotencyKey:key()} : body,
  headers:inBody ? {} : {'Idempotency-Key':key()},
});
export async function otp(email, after=0) {
  for (let attempt=0;attempt<80;attempt++) {
    const search = await fetch(`${mailBase}/api/v1/search?query=${encodeURIComponent('to:'+email)}`, {signal:AbortSignal.timeout(5000)}).then(r=>r.json());
    for (const message of search.messages || []) {
      if (Date.parse(message.Created) < after) continue;
      const content=await fetch(`${mailBase}/api/v1/message/${message.ID}`).then(r=>r.json());
      const match=(content.Text || content.HTML || '').match(/\b\d{6}\b/);
      if (match) return match[0];
    }
    await delay(150);
  }
  throw new Error('Código de autenticação não recebido no SMTP de homologação');
}
export async function login(role='manager') {
  const email=role==='manager'?credentials.managerEmail:role==='concurrent'?credentials.concurrentEmail:credentials.operatorEmail;
  const password=role==='manager'?credentials.managerPassword:credentials.operatorPassword;
  const after=Date.now()-1000;
  const challenge=await api('/auth/login',{method:'POST',body:{email,password},headers:{'X-Client-Type':'MOBILE'}});
  const code=await otp(email,after);
  const session=await api('/auth/challenge/verify',{method:'POST',body:{challengeId:challenge.challengeId,code},headers:{'X-Client-Type':'MOBILE'}});
  assert.equal(typeof session.token,'string','Login precisa retornar token válido');
  return session.token;
}
export async function pageAll(token, resource, filters={}) {
  const all=[];
  for(let page=0;;page++) {
    const query=new URLSearchParams({...filters,page:String(page),size:'100'});
    const data=await api(`/${resource}?${query}`,{token});
    all.push(...data.content);
    if(data.last) return all;
  }
}
export function save(name, data) {
  fs.writeFileSync(path.join(output,name),JSON.stringify(data,null,2)+'\n');
}
