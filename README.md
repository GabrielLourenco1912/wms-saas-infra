# WMS SaaS

Sistema de gerenciamento de armazéns e distribuidores de pequeno e médio porte, desenvolvido como TCC. Este repositório reúne a infraestrutura e fixa as versões dos três submódulos:

| Submódulo | Responsabilidade | Documentação |
| --- | --- | --- |
| `wms-saas-backend` | API Java 21/Spring Boot, regras de negócio, autorização, persistência e auditoria | [API para os clientes](wms-saas-backend/docs/API_CLIENTS.md) |
| `wms-saas-web` | Painel Next.js de gestão, cadastros, planejamento e acompanhamento | [Integração web](wms-saas-web/docs/INTEGRACAO_API.md) |
| `wms_saas_mobile` | Aplicativo Flutter para conferência e execução das operações físicas | [Integração mobile](wms_saas_mobile/docs/INTEGRACAO_API.md) |

O navegador acessa o proxy `/api/backend` do Next.js; o Next.js chama o Spring pela rede interna do Docker. O aplicativo mobile chama diretamente a API publicada. O Spring mantém os dados no MySQL.

## Preparar o repositório

Após clonar, inicialize os submódulos nas versões registradas pela raiz:

```bash
git submodule update --init --recursive
git submodule status
```

As URLs em [.gitmodules](.gitmodules) usam SSH do GitHub e exigem acesso aos respectivos repositórios. Os submódulos podem ficar em `detached HEAD` após a inicialização; crie ou selecione uma branch dentro do submódulo antes de desenvolver. Para reproduzir a entrega, use os commits registrados, sem atualizar automaticamente para as pontas das branches remotas.

## Executar backend e painel

Use Docker com Compose v2 e BuildKit. Em uma instalação nova:

```bash
cp .env.example .env
```

Edite `.env` antes de continuar:

- Preencha `DB_PASSWORD` e `JWT_SECRET`. Gere o segredo JWT com `openssl rand -hex 32`.
- Configure `MAIL_HOST`, `MAIL_PORT`, `MAIL_FROM` e as credenciais/TLS exigidos pelo seu SMTP. O Compose não inclui um servidor de e-mail; `localhost` dentro do backend identifica o próprio contêiner.
- Para acessar o painel por HTTP local, defina `REFRESH_COOKIE_SECURE=false`. Em HTTPS, mantenha `true`.
- Para uma base nova sem gestor, habilite `WMS_BOOTSTRAP_ENABLED=true` e preencha `WMS_BOOTSTRAP_NAME`, `WMS_BOOTSTRAP_EMAIL` e `WMS_BOOTSTRAP_PASSWORD`. Após provisionar, desabilite o bootstrap e remova a senha de provisionamento do `.env`.

Em uma instalação existente, preserve o `.env` e acrescente somente as opções necessárias a partir do exemplo.

```bash
docker compose config --quiet
docker compose build backend web
docker compose up -d --pull never
docker compose ps
```

Com as portas padrão, abra o painel em `http://localhost:3000`. A prontidão da API pode ser consultada em `http://localhost:8080/health/ready`. O MySQL precisa passar pelo healthcheck antes da inicialização do Spring. A ordem de partida do web não significa que o Spring já terminou as migrations; aguarde a prontidão antes de entrar.

O login solicita o código enviado por e-mail. Não há cadastro público nem credenciais fixas de demonstração.

O Compose já injeta `WMS_API_BASE_URL=http://backend:<SERVER_PORT>` no web. Deixe essa variável vazia para usar o endereço interno calculado; preencha somente para apontar para outra API acessível pelo servidor Next.js, sem `/api` ao final. Não é necessário usar o override de exemplo do submódulo web com este Compose.

O banco usa o volume persistente `db_data`. As migrations foram consolidadas para desenvolvimento: se a base foi criada com versões antigas, siga a [orientação do backend](wms-saas-backend/README.md#banco-de-desenvolvimento) para provisionar uma base nova. O comando `docker compose down` conserva o volume; `docker compose down -v` exclui os dados.

Consulte [docker/README.md](docker/README.md) para portas, imagens, configuração, diagnóstico e publicação no GHCR.

## Executar o aplicativo mobile

Com o backend acessível e o Flutter instalado:

```bash
cd wms_saas_mobile
flutter pub get
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8080
```

`10.0.2.2` alcança o host pelo emulador Android. Em aparelho físico, use o endereço do servidor na rede e a porta `BACKEND_PUBLISHED_PORT`. Veja os requisitos e as opções de plataforma no [README mobile](wms_saas_mobile/README.md).

## Verificação

Valide a configuração integrada na raiz com `docker compose config --quiet`. Os Dockerfiles geram as imagens de produção; execute as verificações de cada aplicação separadamente:

| Diretório | Comandos |
| --- | --- |
| `wms-saas-backend` | `./mvnw verify` e `./ops/verify-backup.sh` (Docker necessário para a cobertura MySQL/backup) |
| `wms-saas-web` | `npm ci`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, `npm run test:e2e` |
| `wms_saas_mobile` | `flutter pub get`, `flutter analyze`, `flutter test`, `flutter build apk --debug` |

Os guias de integração registram o que foi validado e os limites dos testes. Homologação em armazém, dispositivos/scanners e implantação de produção permanecem etapas próprias.

Na revisão da raiz em 15/10/2026, foram validados o Compose (padrões, portas alternativas, API externa e encaminhamento das 40 propriedades do backend), o build das duas imagens e um ambiente descartável com MySQL e Spring reais. O teste integrado confirmou migrations V1/V2, quatro gatilhos de proteção do histórico, primeiro gestor, envio/recebimento de código em um SMTP de teste, login pelo proxy, cookie HttpOnly, cadastro persistido, paginação 20, tamanho configurável, pesquisa, seletores de cinco itens, renovação rotativa e logout. Nenhum banco existente ou serviço de e-mail externo foi usado nessa verificação.

## Identidade visual e documentação pública

A marca **WMS SaaS — Gestão de armazéns** usa a direção “Precisão em movimento”, o símbolo W de percurso, Manrope/DM Mono e o crédito de Gabriel Lourenço com Monograma GL / 01. Web, mobile e e-mails compartilham esses elementos.

No painel, `/documentacao` reúne as rotas públicas `/documentacao/api`, `/documentacao/modelo-relacional` e `/documentacao/branding`, acessíveis sem sessão. O guia de branding inclui paleta, tipografia, ícone, autoria e downloads.

Os recursos utilizados são versionados em cada aplicação; builds não dependem dos materiais locais. Manutenção: [web](wms-saas-web/docs/IDENTIDADE_VISUAL.md), [mobile](wms_saas_mobile/docs/IDENTIDADE_VISUAL.md) e [e-mails](wms-saas-backend/docs/IDENTIDADE_EMAILS.md). Os originais e as apresentações ficam localmente em `docs-gerais/identidade-visual/`.

## Alterar e versionar

Faça os commits de uma aplicação dentro do respectivo submódulo. Depois, registre sua nova referência no repositório principal com `git add <submódulo>` e um commit na raiz. Ao publicar, envie primeiro os commits dos submódulos e depois o commit principal, para que um novo clone consiga obter todas as referências.

`docs-gerais/` conserva localmente o artigo, seus modelos e materiais de referência e não entra nos commits. `.env`, credenciais e `backups/` também são ignorados. A documentação técnica versionada fica nos READMEs, em `docker/` e nos diretórios `docs/` dos submódulos.
