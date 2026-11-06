# Homologação e aceitação automatizada do WMS

O ambiente da branch `homol` compartilha os checks de backend, web, mobile e
backup da `main` e acrescenta aceitação com os clientes reais e medições de carga.
Os três submódulos são obtidos nos commits fixados pela raiz. A câmera foi
entregue separadamente na branch `develop` do mobile; `homol` acrescenta os testes.

## Destinos isolados

| Configuração | Homologação |
| --- | --- |
| Environment GitHub | `homologation` |
| Diretório de deploy | `/var/www/wms-saas-homol` |
| Projeto Compose / volume MySQL | `wms-saas-homol` / `wms-saas-homol_db_data` |
| Manifest | `compose.homol.yml` |
| Painel no host | `127.0.0.1:3333` |
| API no host | `127.0.0.1:8888` |
| Banco | `wms_saas_homol`; nenhuma porta publicada |
| Painel público | `https://homol.wms.lourencogabriel.dev` |
| API pública | `https://homol.api.wms.lourencogabriel.dev` |
| Backups | `/var/backups/wms-homol/mysql` |
| Caixa SMTP de teste | Mailpit interno; interface/API somente `127.0.0.1:8026` |

O renderer força os destinos de homologação e recusa JDBC externo nesse modo.
DB, JWT e hashes das contas têm secrets próprios no environment `homologation`.
O servidor de e-mail captura as mensagens localmente, sem entrega a destinatários
reais. O perfil Spring `homol` e a migration V1000 são exclusivos da base
sintética; um callback Flyway rejeita os nomes de banco de produção antes de
executar qualquer migration. Veja o [guia do backend](../wms-saas-backend/docs/HOMOLOGACAO.md).

O Compose limita CPU e memória: backend 1 CPU/1 GiB, MySQL 0,5 CPU/768 MiB,
web 0,5 CPU/384 MiB, Mailpit 0,1 CPU/128 MiB e backup 0,1 CPU/256 MiB.
Os benchmarks são executados no ambiente descartável local/CI; a validação do
host compartilhado é funcional, sem aplicar carga de benchmark em produção.

## CI e deploy

Pushes em `homol` executam os mesmos checks comuns da `main`, mais o job
`homol-acceptance`. Ele inicia MySQL, Spring, Next.js, Mailpit e backup em um
projeto descartável, prepara Android 34 e executa Playwright + Flutter contra os
serviços reais. A publicação no GHCR depende também dessa aceitação.

O publish usa tag `homol` e SHA da raiz. O deploy usa os digests publicados,
environment `homologation`, diretório/projeto fixados acima e sua própria trava.
O manifest de produção permanece `compose.deploy.yml`. `HOMOL_DEPLOY_ENABLED`
controla apenas o deploy da homologação; `DEPLOY_ENABLED` continua controlando
produção. Não é necessário mudar `DEPLOY_DIR` global para instalar homologação.

No environment `homologation`, configure `DB_PASSWORD`, `DB_USERNAME`,
`JWT_SECRET`, `HOMOL_MANAGER_PASSWORD_HASH` e `HOMOL_OPERATOR_PASSWORD_HASH`.
As senhas correspondentes ficam em `HOMOL_MANAGER_PASSWORD` e
`HOMOL_OPERATOR_PASSWORD` para operação/testes; não entram no código ou nos
artefatos. SSH e leitura dos submódulos seguem as configurações existentes da
infraestrutura. Os hashes precisam ser BCrypt válidos.

## Reproduzir localmente

Requer Docker/Compose, Node 22+, Java/Android SDK, Flutter 3.41.9, Chromium do
Playwright e um emulador Android iniciado. Na raiz, prepare o Python isolado:

```bash
python3 -m venv .homol-private/tools
.homol-private/tools/bin/pip install bcrypt==4.3.0
npm --prefix wms-saas-web ci
cd wms-saas-web
npx playwright install chromium
cd ..
PYTHON="$PWD/.homol-private/tools/bin/python" HOMOL_ANDROID_DEVICE=emulator-5580 bash tests/homol/run.sh
```

O script não lê o `.env` da aplicação. Gera credenciais privadas em
`.homol-private/`, cria projeto/volume próprios e remove somente esse projeto no
fim. `HOMOL_KEEP_ENVIRONMENT=1` conserva o ambiente de uma execução para diagnóstico.
As portas 3333/8888/8026 precisam estar livres. `HOMOL_ARTIFACT_DIR` altera o
destino das evidências; por padrão ficam em `artifacts/homol/<execução>/`.

O teste usa a autenticação completa. O Playwright prepara entrada, pedido e onda;
o Flutter executa as confirmações físicas por entrada de texto no Android; o
driver confere os efeitos na API. As verificações adicionais cobrem permissões,
FEFO/FIFO, divergência, bloqueios, transferências, inventário, cancelamento e
reenvio. O código do driver não integra o backend e não cria endpoints de bypass.

## Medições e artefatos

O [protocolo versionado](../tests/homol/performance-protocol.json) foi definido
antes dos ensaios: 10/50/200 pedidos de um item, dez repetições por tamanho,
60 confirmações de recebimento sem ondas e 60 com ondas concorrentes, usando
atores distintos no mesmo armazém. Cada operação usa documentos/chaves novos.
O limite de 200 respeita o contrato real de uma onda.

Os limites locais são p95 de geração inferior a 5 s e p95 HTTP de confirmação
inferior a 2 s, com todos os comandos aprovados. O segundo limite é um controle
HTTP; não substitui RNF004, que depende do feedback completo no dispositivo.
O conjunto é sintético e não estabelece capacidade de produção ou escala para
pedidos com mais itens/lotes. Os resultados incluem máximos e falhas.

Arquivos principais: `acceptance-results.json`, `scenario.json`, capturas PNG,
`mobile-results.json`, `benchmark-workload.json`, amostras JSON/CSV, sumários k6,
`benchmark-results.json` e `manifest.json` com revisões e hashes. Credenciais e
planos privados de autenticação não são enviados como artefatos.

## Verificação manual em aparelho

O APK de homologação aponta para o domínio homol da API. O build com
`CAPTURE_FEEDBACK_METRICS=true` disponibiliza no perfil a tela **Medições de
homologação**, com cópia de CSV. O relógio começa na captura aceita ou no término
do código pelo teclado e termina no primeiro quadro de feedback confirmado;
inclui a espera até confirmar o formulário. Não coleta códigos ou tokens.

Para consultar os e-mails a partir do computador, abra um túnel SSH:

```bash
ssh -N -i ~/.ssh/cicd-deploy -L 18026:127.0.0.1:8026 root@lourencogabriel.dev
```

Abra `http://127.0.0.1:18026`. As contas e os identificadores de exemplo constam
no guia do backend. As credenciais geradas na preparação desta entrega ficam em
arquivo local privado, não no artigo ou no repositório.

A câmera física, permissões do aparelho, pausa/retomada, leitura de etiquetas e
feedback em Android físico são verificações manuais finais. A entrada de texto
automatizada no emulador não comprova captura óptica. Luvas, scanners externos e
homologação em empresa seguem a delimitação de trabalhos futuros do artigo.
