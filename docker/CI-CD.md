# CI/CD com GitHub Actions, GHCR e Ubuntu

O [workflow CI/CD](../.github/workflows/ci-cd.yml) fica no **repositório raiz de infraestrutura**, que fixa os commits dos três submódulos. Alterações de uma aplicação entram na entrega quando seu commit é registrado e enviado na raiz. O checkout não acompanha automaticamente as branches dos submódulos.

## Fluxo

PRs para `develop`/`main`, pushes em qualquer branch e execuções manuais executam todos os testes. Publicação e deploy ficam restritos a `develop`/`main` fora de PRs. O fluxo é:

1. Em runners GitHub `ubuntu-24.04`, executam em paralelo:
   - Backend: Java 21, `./mvnw -B -ntp clean verify`, H2 e MySQL/Testcontainers. O CI falha se qualquer teste for ignorado ou se as duas suítes MySQL não executarem.
   - Web: Node 22, `npm ci`, lint, tipos, testes unitários, build e Playwright/Chromium para a aplicação e a documentação pública.
   - Mobile: Flutter 3.41.9/Dart 3.11.5, lockfile obrigatório, análise, testes e APK debug. O APK é artefato de validação; distribuição e assinatura de produção ficam fora deste deploy.
   - Backup: suíte Bash existente, com MySQL descartável, migrations do WMS, restauração, retenção, concorrência e cron real. Não usa o `.env` nem os volumes da aplicação.
   - Infraestrutura: sintaxe Bash, ShellCheck e testes da configuração e dos limites de falha do deploy.
2. Somente após todas as verificações passarem, constroem e publicam backend, web e backup no GHCR. As tags são `sha-<commit-da-raiz>` e `develop`/`main`; o cache é separado por imagem e branch. Os builds não recebem credenciais de produção.
3. Com `DEPLOY_ENABLED=true`, na branch `DEPLOY_BRANCH` (padrão `main`), o job do environment `production` envia um pacote privado por SSH. O Ubuntu recebe apenas Compose, configuração e script; faz login temporário no GHCR, pull e `up --no-build --pull never`, aguardando os healthchecks. **As três imagens são implantadas por digest**, independentemente das tags mutáveis.

Execuções da mesma branch são serializadas. Deploys têm uma trava no GitHub e outra no host. PRs antigos podem ser cancelados. Configure a proteção de branch para exigir o check **CI aprovado**.

## Configurar o GitHub

Cadastre controles do pipeline em **Settings → Secrets and variables → Actions** do repositório raiz; cadastre runtime e SSH em **Settings → Environments → production**. O workflow não cria esses cadastros.

Se a raiz ainda não tiver um remote GitHub, publique-a em um repositório próprio antes de usar Actions. Push apenas do backend não aciona este fluxo. Envie primeiro os commits dos submódulos e depois o commit da raiz.

### Variables do repositório

| Nome | Padrão / finalidade |
| --- | --- |
| `GHCR_NAMESPACE` | Dono do repositório, convertido para minúsculas. Conta/organização de destino; o token do workflow precisa poder publicar ali. |
| `DEPLOY_ENABLED` | Ausente/`false`: testes e publicação. Defina `true` após preparar servidor e environment. |
| `DEPLOY_BRANCH` | `main`. Para entregar esta branch de desenvolvimento automaticamente, configure `develop`. Apenas `main`/`develop` publicam. |
| `MOBILE_API_BASE_URL` | `https://api.wmssaas.com`; endereço compilado no APK debug. |

### Variables do environment `production`

Use texto sem aspas externas ou sintaxe de shell. Os padrões completos estão em [render-deploy-env.py](../scripts/render-deploy-env.py).

| Nomes | Configuração |
| --- | --- |
| `DEPLOY_HOST`, `DEPLOY_USER` | **Obrigatórios**: IP/DNS e usuário SSH do Ubuntu. |
| `DEPLOY_PORT`, `DEPLOY_DIR`, `DEPLOY_PROJECT_NAME` | `22`, `/opt/wms-saas`, `wms-saas`. Diretório dedicado, absoluto, sem espaços. Projeto define a rede e o volume MySQL. |
| `DEPLOY_WAIT_TIMEOUT` | `240` segundos para prontidão das aplicações; aceita 30 a 1800. O job tem limite total de 20 minutos. |
| `PUBLISHED_BIND_ADDRESS` | `127.0.0.1`, para usar o reverse proxy do host. |
| `BACKEND_PUBLISHED_PORT`, `WEB_PUBLISHED_PORT` | `8080`, `3000`; escolha portas livres ou já pertencentes ao projeto WMS. |
| `SERVER_PORT`, `WEB_PORT`, `WEB_HOSTNAME` | `8080`, `3000`, `0.0.0.0`: portas/endereço internos. |
| `WMS_API_BASE_URL` | Vazio calcula `http://backend:<SERVER_PORT>`. API externa: URL acessível pelo web, sem `/api` final. |
| `MAIL_HOST`, `MAIL_FROM`, `CORS_ALLOWED_ORIGINS` | **Obrigatórios**: SMTP acessível pelo backend, remetente e origens HTTPS do cliente separadas por vírgulas. |
| `MAIL_PORT`, `MAIL_SMTP_AUTH`, `MAIL_STARTTLS_ENABLED` | Padrões de deploy: `587`, `true`, `true`. Ajuste ao provedor; os padrões locais são diferentes. |
| `MAIL_CONNECTION_TIMEOUT`, `MAIL_READ_TIMEOUT`, `MAIL_WRITE_TIMEOUT` | `5000` ms. |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `MYSQL_IMAGE` | `mysql`, `3306`, `wms_saas`, `mysql:8.0`; compatíveis com a infraestrutura atual. Upgrades de banco são operações separadas. |
| `JWT_ISSUER`, `REFRESH_COOKIE_SECURE` | `https://api.wmssaas.com`, `true`. Cookie inseguro somente em desenvolvimento HTTP. |
| `MYSQL_BACKUP_HOST`, `MYSQL_BACKUP_PORT`, `MYSQL_BACKUP_HOST_DIR`, `MYSQL_BACKUP_RETENTION_DAYS` | `mysql`, `3306`, `/var/backups/wms/mysql`, `30`. Diretório exclusivo e persistente. Retenção mínima de 30 dias. |
| `MYSQL_RESTORE_HOST`, `MYSQL_RESTORE_PORT` | Vazios reutilizam a conexão do backup. Restauração manual. |
| `WMS_BOOTSTRAP_ENABLED`, `WMS_BOOTSTRAP_NAME` | `false`, `Gestor inicial`. Habilite somente no provisionamento do primeiro gestor. |
| `AUTH_CHALLENGE_TTL`, `AUTH_CHALLENGE_MAX_ATTEMPTS` | `10m`, `5`. |
| `ACCOUNT_LOCK_MAX_FAILED_ATTEMPTS`, `ACCOUNT_LOCK_DURATION`, `ACCOUNT_LOCK_UNLOCK_INTERVAL`, `ACCOUNT_LOCK_SCHEDULER_ENABLED` | `5`, `15m`, `60000`, `true`. |
| `SPRING_APPLICATION_NAME`, `SPRING_THREADS_VIRTUAL_ENABLED`, `NEXT_TELEMETRY_DISABLED` | `wms-saas`, `true`, `1`. |
| `SPRING_JPA_OPEN_IN_VIEW`, `SPRING_JPA_SHOW_SQL`, `SPRING_MVC_PROBLEMDETAILS_ENABLED` | `false`. |
| `SPRING_JPA_HIBERNATE_DDL_AUTO`, `FLYWAY_BASELINE_ON_MIGRATE`, `FLYWAY_BASELINE_VERSION` | `validate`, `false`, `1`. O gerador recusa criação/atualização de schema pelo Hibernate e baseline automática. |
| `FREEMARKER_TEMPLATE_LOADER_PATH`, `FREEMARKER_SUFFIX`, `FREEMARKER_CHARSET`, `FREEMARKER_CHECK_TEMPLATE_LOCATION` | `classpath:/templates/`, `.ftlh`, `UTF-8`, `true`. |

### Secrets

| Nome / local | Finalidade |
| --- | --- |
| `SUBMODULES_TOKEN` / repositório | Para submódulos privados: PAT com leitura de Contents nos três repositórios e na raiz. Sem esse secret, usa `GITHUB_TOKEN`, suficiente para submódulos públicos. PRs de forks não recebem secrets para ler submódulos privados. |
| `DEPLOY_SSH_PRIVATE_KEY` / `production` | Chave privada dedicada, sem passphrase; publique a chave pública correspondente no `authorized_keys` do usuário do host. |
| `DEPLOY_SSH_KNOWN_HOSTS` / `production` | Chave SSH **verificada** do host no formato `known_hosts`; porta alternativa usa `[host]:porta`. Não há descoberta automática da chave durante o deploy. |
| `DB_PASSWORD`, `JWT_SECRET` / `production` | **Obrigatórios**. Para um banco novo, gere a senha com `openssl rand -hex 32`, compatível com a inicialização da imagem MySQL. JWT: pelo menos 32 bytes UTF-8. Preserve os valores do banco existente; mudar o secret não altera a senha de um MySQL já inicializado. |
| `DB_USERNAME` / `production` | Ausente mantém `root`, compatível com o Compose atual. Conta da aplicação deve ser provisionada antes de configurá-la. |
| `DB_URL` / `production` | Opcional. URL JDBC completa; secret porque pode conter parâmetros sensíveis. Vazia usa host/porta/nome do banco. |
| `SPRING_FLYWAY_URL`, `SPRING_FLYWAY_USER`, `SPRING_FLYWAY_PASSWORD` / `production` | Conta administrativa opcional para migrations/gatilhos; vazios reutilizam a conexão da aplicação. |
| `MAIL_USERNAME`, `MAIL_PASSWORD` / `production` | Credenciais SMTP, conforme o provedor. |
| `WMS_BOOTSTRAP_EMAIL`, `WMS_BOOTSTRAP_PASSWORD` / `production` | Exigidos com bootstrap habilitado. Após provisionar, desabilite a variável e remova os secrets. |
| `MYSQL_BACKUP_USERNAME`, `MYSQL_BACKUP_PASSWORD` / `production` | Vazios reutilizam credenciais do banco; consulte as permissões de conta dedicada no [guia de backup](mysql-backup/README.md). |
| `MYSQL_RESTORE_USERNAME`, `MYSQL_RESTORE_PASSWORD` / `production` | Opcionais, para restauração manual. Vazios reutilizam as credenciais do backup. |

O publish usa `GITHUB_TOKEN` com `packages: write`; o deploy usa seu próprio token com `packages: read`, enviado por stdin SSH para `docker login --password-stdin`. As credenciais Docker são temporárias e removidas mesmo em falhas. Não é preciso PAT de GHCR no servidor. Para packages já existentes/vinculados a outros repositórios, conceda acesso ao repositório raiz em **Package settings → Manage Actions access**.

## Preparar o Ubuntu uma vez

Requisitos: Bash, OpenSSH, `tar`, `flock`/util-linux, Docker Engine e Compose v2 ou superior com `--wait` e `pull --policy missing`. As imagens são `linux/amd64`; confirme `x86_64` no host. O usuário SSH precisa executar Docker sem `sudo` interativo e escrever no diretório dedicado. Não precisa de Git, Maven, Node ou Flutter.

Exemplo para usuário existente `ubuntu`:

```bash
sudo install -d -m 700 -o ubuntu -g ubuntu /opt/wms-saas
docker info
docker compose version
```

Instale a chave pública dedicada e confira a identidade SSH por um canal confiável antes de cadastrar `DEPLOY_SSH_KNOWN_HOSTS`. O runner GitHub precisa chegar à porta SSH e o host precisa acessar o GHCR. O pipeline não altera firewall, proxy ou instalação do Docker.

Mantenha `DEPLOY_PROJECT_NAME` estável. Para adotar uma instalação WMS existente, use o projeto Compose atual (`docker compose ls`) e preserve `<projeto>_db_data`, senha, JWT e caminho de backups. Outro nome de projeto cria um banco novo. O manifest de deploy remove nomes globais de containers e acrescenta healthchecks; revise a primeira transição e faça backup antes.

Aponte o proxy HTTPS do host para `127.0.0.1:<WEB_PUBLISHED_PORT>` e, para o mobile, para `127.0.0.1:<BACKEND_PUBLISHED_PORT>`. Configure as URLs correspondentes em `CORS_ALLOWED_ORIGINS` e `MOBILE_API_BASE_URL`. O MySQL não publica porta no host.

Depois, defina `DEPLOY_ENABLED=true`, escolha `DEPLOY_BRANCH` e faça push ou use **Actions → CI/CD → Run workflow** nessa branch. Para revisar esta entrega em `develop` sem implantar, deixe `DEPLOY_ENABLED` ausente/`false`. A interface de execução manual exige que o workflow também esteja na branch padrão do GitHub.

## Operação e falhas

O pacote fica em `/opt/wms-saas/.releases/<commit>-<run>-<tentativa>/`. A árvore é privada e o `.env` tem permissão `0600`. A configuração é regenerada a cada entrega, preserva caracteres especiais e nunca é executada como Bash. Não use `source .env` nem publique o arquivo em logs/artefatos.

Todos os pulls e o `mysql-backup check` terminam antes da atualização. MySQL inicia com `--no-recreate`; aplicações usam `--no-deps`, preservando o container/configuração do banco existente. Mudanças administrativas do banco devem ser feitas separadamente. O web exige sucesso na página de login e na chamada interna à prontidão do backend. O healthcheck do backup monitora cron; acompanhe também logs e arquivos dos dumps diários.

`current` e `previous` registram as duas últimas entregas concluídas. Uma falha durante `up` pode deixar aplicações parcialmente atualizadas; o job falha sem promover `current`. Não há rollback automático porque migrations podem impedir retorno de versão. A troca de containers pode causar breve indisponibilidade.

Diagnóstico, usando o nome real de `DEPLOY_PROJECT_NAME`:

```bash
cd /opt/wms-saas/current
docker compose --project-name wms-saas --env-file .env -f compose.deploy.yml ps
docker compose --project-name wms-saas --env-file .env -f compose.deploy.yml logs --tail 100 backend web mysql-backup
docker compose --project-name wms-saas --env-file .env -f compose.deploy.yml run --rm --no-deps mysql-backup backup
```

Não execute `docker compose config` sem `--quiet`: a saída contém credenciais. Para retorno manual, avalie a compatibilidade do schema e execute o Compose e `.env` da pasta anterior com `up --detach --no-build --pull never --no-deps --wait backend web mysql-backup`. As imagens precisam estar locais; se faltarem, autentique-se temporariamente com uma credencial GHCR de leitura e faça pull antes. O retorno manual não altera os links das entregas concluídas.

O deploy não executa `down`, remoção de volumes ou limpeza global do Docker. Releases anteriores e imagens são conservadas para investigação/retorno; gerencie sua retenção conforme o espaço, lembrando que cada pasta contém configuração sensível. A cópia externa e o acompanhamento diário dos backups continuam necessários.

## Validação desta entrega

Em 04/11/2026: 452 testes do backend sem testes ignorados, 77 testes unitários do web, 14 cenários de navegador, 9 da documentação pública e 66 testes do mobile; APK debug compilado. Backup/restauração, retenção e cron passaram na suíte descartável. Actionlint, ShellCheck, os sete testes de configuração e os oito cenários dos scripts passaram.

As três imagens foram construídas localmente. Um projeto Compose descartável confirmou prontidão, geração de backup, preservação do mesmo container MySQL entre releases e recusa de promover uma release com web realmente não saudável. SSH e GHCR em produção dependem dos cadastros acima; nenhuma aplicação do host de produção foi acessada nessa validação.

Referências oficiais: [GHCR com Actions](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images), [autenticação/permissões do registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry), [Compose up](https://docs.docker.com/reference/cli/docker/compose/up/).
