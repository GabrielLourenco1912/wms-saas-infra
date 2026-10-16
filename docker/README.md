# Contêineres do WMS

Executar os comandos na raiz `TCC_WMS`, onde ficam `docker-compose.yml` e `.env`.

## Configuração

Copiar `.env.example` para `.env` em uma instalação nova e preencher `JWT_SECRET` e `DB_PASSWORD`. Gerar o segredo JWT com `openssl rand -hex 32`. Em uma instalação existente, conservar os valores de banco, JWT e SMTP e acrescentar as novas chaves do exemplo.

As propriedades do `wms-saas-backend/src/main/resources/application.yaml` usam variáveis de ambiente. Todas estão no exemplo da raiz e são encaminhadas pelo `environment` do serviço `backend`. O backend também tem seu próprio `.env.example`, com os parâmetros para execução fora do Compose.

`DB_URL` vazio monta a URL JDBC usando `DB_HOST`, `DB_PORT` e `DB_NAME`. Uma URL preenchida tem precedência. O serviço MySQL conserva o volume `db_data` e usa `DB_PASSWORD` como senha de root; o usuário inicial padrão da aplicação é `root`. Alterar senha ou nome da base no `.env` não reconfigura um volume MySQL já inicializado. Se usar outro usuário de aplicação, provisione-o no banco com os privilégios necessários; o Compose não o cria automaticamente.

Configurar `MAIL_HOST` com um servidor SMTP acessível pelo contêiner. `localhost` dentro de um contêiner aponta para o próprio contêiner. Não há serviço SMTP neste Compose. A autenticação depende do envio de códigos de uso único; configure host, porta, remetente, autenticação e TLS antes de testar o login.

`SERVER_PORT` controla a porta interna do backend e `BACKEND_PUBLISHED_PORT` sua publicação no host. `WEB_PORT` controla a porta interna do Next.js e `WEB_PUBLISHED_PORT` sua publicação no host. Se mudar a origem web, atualizar também `CORS_ALLOWED_ORIGINS`. `REFRESH_COOKIE_SECURE=false` permite o fluxo web durante desenvolvimento em HTTP.

O serviço web recebe `WMS_API_BASE_URL` em execução. Vazio ou ausente, o valor é calculado como `http://backend:<SERVER_PORT>`; uma URL explícita tem precedência e deve apontar à origem da API acessível pelo contêiner, sem `/api` no final. A porta publicada no host não altera esse endereço interno. O navegador usa `/api/backend` na origem do próprio painel, e o proxy Next.js encaminha a chamada para o Spring. O Compose principal já faz a integração; o override de exemplo do submódulo web é opcional e fixa a porta da API em 8080.

Atrás de um proxy reverso HTTPS, preserve o cabeçalho `Host` original e encaminhe corretamente `X-Forwarded-Proto`, pois o painel confere a origem das mutações. Mantenha `REFRESH_COOKIE_SECURE=true` nesse ambiente.

A configuração não faz baseline automático de bancos existentes: `FLYWAY_BASELINE_ON_MIGRATE=false` continua sendo o padrão. As migrations foram consolidadas para desenvolvimento; bancos das versões anteriores exigem uma base nova e vazia, conforme a seção [Banco de desenvolvimento](../wms-saas-backend/README.md#banco-de-desenvolvimento). Não use baseline para pular a criação das tabelas.

Para o primeiro gestor, habilite `WMS_BOOTSTRAP_ENABLED`, preencha nome/e-mail/senha e inicie o backend. Desabilite o bootstrap e remova a senha de provisionamento após a criação. Não existe cadastro público; o primeiro login também exige confirmação por e-mail.

## Imagens e build

| Serviço | Imagem padrão | Contexto | Dockerfile |
| --- | --- | --- | --- |
| Backend | `ghcr.io/gabriellourenco1912/wms-saas-backend:latest` | `wms-saas-backend/` | `docker/backend/Dockerfile` |
| Web | `ghcr.io/gabriellourenco1912/wms-saas-web:latest` | `wms-saas-web/` | `docker/web/Dockerfile` |

`GHCR_NAMESPACE` altera a conta/organização, em minúsculas, e `IMAGE_TAG` altera a tag de ambas as imagens.

Os Dockerfiles separam compilação de execução, usam UID/GID `1001:1001` e incluem o rótulo OCI com o repositório de origem. O backend compila com Maven/Java 21 e executa no JRE 21. O web compila com Node 22 e executa o servidor Next.js standalone, com arquivos estáticos e `public` copiados para a imagem final. A saída standalone contém os arquivos necessários ao servidor, conforme a [documentação do Next.js](https://nextjs.org/docs/app/api-reference/config/next-config-js/output).

Os `.dockerignore` ficam na raiz de cada contexto. Enviam apenas entradas de produção: POM e `src/main` no backend; código, arquivos de configuração, lockfile e `public` no web. Dependências locais, `.next`, `target`, testes Java, Git, IDEs, documentação e arquivos `.env` não entram no contexto. Dependências do build usam cache do BuildKit.

```bash
docker compose config --quiet
docker compose build backend web
docker compose up -d --pull never
```

O healthcheck do MySQL executa `SELECT 1` autenticado na base configurada, e o backend aguarda seu sucesso antes de iniciar. O web parte depois do contêiner backend e consulta a API real. Essa ordem não aguarda a conclusão das migrations do Spring. Consulte a prontidão antes de testar o acesso:

```bash
docker compose ps
docker compose logs --tail=100 backend web
curl --fail http://localhost:8080/health/ready
```

No último comando, ajuste a porta se `BACKEND_PUBLISHED_PORT` não for 8080. A rota `/health/ready` retorna 200 somente quando a API consegue consultar o banco.

O aplicativo Flutter executa fora deste Compose e acessa a porta publicada do backend. No emulador Android, use `http://10.0.2.2:8080`; em aparelho físico, o endereço de rede do servidor.

Para construir diretamente com a nomenclatura padrão:

```bash
docker build -f docker/backend/Dockerfile -t ghcr.io/gabriellourenco1912/wms-saas-backend:latest wms-saas-backend
docker build -f docker/web/Dockerfile -t ghcr.io/gabriellourenco1912/wms-saas-web:latest wms-saas-web
```

## GHCR: enviar e baixar

O GHCR aceita os nomes `ghcr.io/<conta-ou-organizacao>/<imagem>:<tag>`. Para enviar imagens, autenticar o Docker com um PAT classic com `write:packages`; para baixar imagens privadas, usar `read:packages`. Os rótulos `org.opencontainers.image.source` associam as imagens aos repositórios. Referência: [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

```bash
docker login ghcr.io -u GabrielLourenco1912
docker compose build backend web
docker compose push backend web
```

Para executar imagens já publicadas, definir o namespace e a tag desejados no `.env`:

```bash
docker compose pull backend web
docker compose up -d --no-build --pull never
```

O envio ao GHCR é feito explicitamente pelo comando de push; o build local produz as duas imagens já com suas tags de registry.

## Dados e diagnóstico

`docker compose down` encerra os serviços conservando o volume. A opção `-v` remove o volume e seus dados. Backup e restauração são tratados pelos [scripts do backend](../wms-saas-backend/README.md#backup-e-restauração); agendamento, monitoramento e armazenamento dos backups precisam ser configurados no ambiente de destino.

| Sintoma | Verificação |
| --- | --- |
| Web retorna 503 ao chamar `/api/backend/...` | Confira `WMS_API_BASE_URL`, a porta interna `SERVER_PORT`, os logs e `/health/ready`; o web não deve usar `localhost` para acessar outro contêiner. |
| Login não envia código | Confira SMTP e logs do backend; o servidor precisa ser alcançável de dentro do contêiner. |
| Sessão se perde ao recarregar em HTTP | Use `REFRESH_COOKIE_SECURE=false` no desenvolvimento local e refaça o login. |
| MySQL permanece sem saúde após alterar o `.env` | Confira as credenciais e a base realmente existentes no volume. As variáveis de inicialização não alteram um banco já criado. |
| Erro de checksum do Flyway em banco antigo | Siga a orientação para base nova de desenvolvimento e preserve os dados antigos necessários. |
| Submódulo vazio ou versão antiga após clonar | Execute `git submodule update --init --recursive`; confirme que os commits dos submódulos foram publicados antes da raiz. |
