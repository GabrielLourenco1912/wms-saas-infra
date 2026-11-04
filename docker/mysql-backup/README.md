# Backup MySQL do WMS

O [CI/CD da infraestrutura](../CI-CD.md) executa esta suíte junto com os testes das três aplicações e só então publica as imagens. O workflow isolado de backup foi incorporado ao fluxo integrado.

O serviço `mysql-backup` integra o Compose padrão e exporta o banco por TCP,
usando clientes Oracle MySQL 8.0. O cron roda diariamente às **02h15 no fuso do
host**, herdado de `/etc/localtime`; logs e nomes de arquivos usam UTC.
Não há backup imediato na inicialização nem reposição de horários perdidos.

## Configuração e primeira execução

Use o mesmo `.env` da aplicação. O Compose transmite apenas as variáveis
declaradas no serviço; o arquivo não é copiado para a imagem nem executado como
script. As opções estão em [../../.env.example](../../.env.example):

| Variável no `.env` | Padrão / finalidade |
| --- | --- |
| `DB_NAME` | `wms_saas`; origem do dump e nome proibido para restauração |
| `MYSQL_BACKUP_HOST` / `MYSQL_BACKUP_PORT` | `mysql` / `3306` |
| `MYSQL_BACKUP_USERNAME` / `MYSQL_BACKUP_PASSWORD` | Vazias reutilizam `DB_USERNAME` / `DB_PASSWORD` (usuário padrão `root`) |
| `MYSQL_BACKUP_HOST_DIR` | `/var/backups/wms/mysql` no host, montado em `/backups` |
| `MYSQL_BACKUP_RETENTION_DAYS` | `30`; aceita inteiros de 30 a 36500 |
| `MYSQL_RESTORE_HOST` / `MYSQL_RESTORE_PORT` | Vazias reutilizam a conexão do backup |
| `MYSQL_RESTORE_USERNAME` / `MYSQL_RESTORE_PASSWORD` | Vazias reutilizam as credenciais do backup |

O banco de origem vem de `DB_NAME`; o caminho interno é sempre `/backups`.
Para bancos externos, configure as opções de conexão do backup explicitamente;
elas não são extraídas de `DB_URL`. Nomes de banco aceitam 1–64 letras ASCII,
números e underscores, exceto bancos de sistema; portas aceitam 1–65535.

Na raiz do projeto, depois de preencher o `.env`:

```bash
chmod 600 .env
docker compose config --quiet
docker compose build mysql-backup
docker compose run --rm --no-deps mysql-backup check
docker compose up -d --wait mysql
docker compose run --rm --no-deps mysql-backup backup
docker compose up -d --no-deps --no-build --wait mysql-backup
```

`check` valida configuração e escrita no diretório; não conecta ao MySQL nem
comprova os grants. `--no-deps` não inicia o banco. Exija saída zero, mensagem
`backup completed` e um arquivo completo antes de considerar a primeira
exportação validada. O Docker pode criar o diretório do host e o script aplica
modo `0700`; cada arquivo publicado recebe `0600`. Em SELinux, prepare a
política para o diretório de backups sem aplicar relabel ao `/etc/localtime`.

Credenciais com `$` e outros caracteres especiais devem usar aspas simples no
`.env`. As senhas são fornecidas aos clientes por `MYSQL_PWD`, sem argumentos
de linha de comando. Não grave a configuração completa renderizada pelo
Compose nem use xtrace, pois o ambiente contém credenciais.

Para uma conta exclusiva de exportação, execute como administrador no MySQL,
adaptando banco, senha e alcance de rede:

```sql
CREATE USER 'wms_backup'@'%' IDENTIFIED BY '<senha definida no servidor>';
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT ON `wms_saas`.* TO 'wms_backup'@'%';
GRANT SHOW_ROUTINE ON *.* TO 'wms_backup'@'%';
```

Configure essa conta em `MYSQL_BACKUP_USERNAME` e `MYSQL_BACKUP_PASSWORD`.
A conta de exportação não precisa escrever dados; restauração exige uma conta
com privilégios de criação/importação no destino. A ferramenta não cria contas
nem altera grants. O MySQL deste projeto usa `DB_PASSWORD` como senha de root;
alterá-la no `.env` não atualiza um volume já inicializado.

## Funcionamento e operação

O dump inclui estrutura, dados, índices, views, rotinas, eventos e triggers.
Usa `--single-transaction --quick --routines --events --triggers --hex-blob`,
`--no-tablespaces --set-gtid-purged=OFF --column-statistics=0`, charset utf8mb4
e `--skip-add-drop-table`. Não usa `--databases` ou `--all-databases`.
A consistência transacional é para InnoDB; coordene migrations e DDL com a
janela de exportação.

Um arquivo como `wms_saas_20261030T051500Z_aB12cD34.sql.gz` contém o SQL gzipado,
com cabeçalho `-- wms-mysql-backup-v1` e identificação do banco de origem.
O sufixo aleatório evita colisões entre execuções no mesmo segundo.
O dump passa diretamente ao gzip com `pipefail`, sem SQL intermediário em disco.
Só após `gzip -t` o `.partial` é renomeado no mesmo diretório para `.sql.gz`.

A retenção roda **somente após publicar um novo backup** e considera o mtime:
remove apenas arquivos regulares desse banco, no primeiro nível, com o padrão
exato gerado pela ferramenta. Preserva outros arquivos e bancos. Trinta dias
não significam trinta arquivos. Falhas de dump/compactação preservam os backups
completos anteriores e não disparam retenção. Se o disco lotar antes do dump,
é necessário liberar espaço por administração do armazenamento.

Backup e restauração compartilham `flock` em `/backups/.mysql-backup.lock`.
Uma operação concorrente falha imediatamente com código **75**. Não apague o
arquivo de trava. Temporários são removidos na saída; parciais deixados por
SIGKILL ou falta de energia são removidos pelo próximo backup sob a trava.

```bash
docker compose run --rm --no-deps mysql-backup backup
docker compose logs --since 48h mysql-backup
docker compose exec mysql-backup date '+%Y-%m-%d %H:%M:%S %Z %z'
docker compose exec mysql-backup cat /etc/cron.d/mysql-backup
sudo ls -lh /var/backups/wms/mysql
```

Após mudar `.env` ou o fuso do host, recrie o serviço:

```bash
docker compose up -d --no-deps --no-build --force-recreate --wait mysql-backup
```

O healthcheck confirma que cron está vivo. Verifique também idade e tamanho do
último arquivo, `backup completed`, erros e espaço livre. O Docker mantém até
três logs de 10 MB; comandos manuais escrevem no terminal. Erros brutos do MySQL
são capturados em temporários privados e descartados para evitar divulgar SQL,
usuários ou dados. Não há alerta externo nem monitoramento de sucesso automático.

## Restauração manual

Use arquivos confiáveis produzidos por esta ferramenta. Prepare um MySQL de
recuperação isolado, com `event_scheduler=OFF`, um banco de destino existente,
vazio e diferente de `DB_NAME`, e uma conta com privilégios de importação:

```sql
CREATE DATABASE `wms_restore_validacao`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
GRANT ALL PRIVILEGES ON `wms_restore_validacao`.* TO 'usuario_restore'@'%';
```

O exemplo de grant pressupõe uma conta já criada pelo administrador. Objetos
com outros `DEFINER` e rotinas em servidores com binlog podem exigir permissões
adicionais, como `SET_USER_ID`. Configure `MYSQL_RESTORE_*` no `.env` para a
conexão de recuperação; preserve `DB_NAME` como o banco original do arquivo.
Não execute backend, migrations ou outros escritores no destino durante a
importação.

Substitua o nome ilustrativo pelo arquivo real, usando o caminho interno:

```bash
docker compose run --rm --no-deps mysql-backup restore \
  /backups/wms_saas_20261030T051500Z_aB12cD34.sql.gz wms_restore_validacao
```

A ferramenta recusa o banco operacional mesmo em outro host, bancos de sistema,
destinos com tabelas/views/rotinas/eventos/triggers e event scheduler ativo.
Também verifica gzip e cabeçalho, recusa symlinks e `.partial`, e bloqueia formas
usuais de `USE` e `CREATE/DROP/ALTER DATABASE`. Esse filtro previne erros comuns;
não é um sandbox de SQL. Revise referências qualificadas ao banco original e
`DEFINER` de objetos. A visibilidade dos objetos depende dos grants da conta.

O SQL inteiro é descompactado em `/tmp` privado antes de qualquer importação.
Como `/tmp` usa tmpfs, reserve espaço para o SQL descompactado; arquivos grandes
podem exigir override com armazenamento temporário privado em disco.
O cliente usa `--binary-mode --local-infile=0` e para no primeiro erro, sem
`--force`. **Uma falha pode deixar o destino parcialmente preenchido**, pois
DDL faz commits implícitos. A ferramenta não apaga o destino; investigue a
falha e prepare outro banco vazio antes de repetir.

Após restaurar, confira tabelas, contagens e amostras de dados, perfis iniciais,
relacionamentos, índices e gatilhos de imutabilidade do histórico WMS. Valide
views, rotinas e eventos antes de executá-los. A ferramenta não altera a
conexão da aplicação.

## Testes e publicação

O registro da execução local está em [VALIDATION.md](VALIDATION.md).

Inicialize os submódulos e execute na raiz, com Bash e Docker Compose v2:

```bash
bash -n docker/mysql-backup/mysql-backup docker/mysql-backup/tests/integration.sh
bash docker/mysql-backup/tests/integration.sh
```

A integração cria projeto Compose aleatório, credenciais temporárias, MySQL
8.0 em tmpfs, sem publicar portas ou usar o `.env` real e `db_data`. Confere
UTF-8, views, funções, procedures, eventos, gatilhos executados, retenção de
30/45 dias, falhas sem perda de backups, concorrência, destinos protegidos,
arquivos corrompidos, importação parcial e ausência de senhas nos logs.
Também aplica as migrations reais V1/V2 do backend e restaura tabelas, perfis,
dados de armazém e um gatilho exercitado de fato, preservando a cobertura do
backup anterior. Os testes removem seus containers, rede, imagem e arquivos.

Um cron real roda com agenda temporária de um minuto; a produção é conferida
separadamente como 02h15. Essa etapa pode aguardar até 75 segundos. O teste
usa a mesma imagem e proteções de filesystem do serviço de produção.

O [workflow integrado](../../.github/workflows/ci-cd.yml) testa em PRs para
`develop`/`main` e, em pushes nessas branches, publica as três imagens somente
após os testes de todas as aplicações e do backup. As tags são `develop`/`main`
e `sha-<commit-da-raiz>`. Submódulos privados usam `SUBMODULES_TOKEN` com leitura;
o publish usa `GITHUB_TOKEN` com `packages: write`. O deploy opcional no Ubuntu
usa imagens por digest e configuração de Variables/Secrets do GitHub, conforme
o [guia de CI/CD](../CI-CD.md). No Compose de desenvolvimento, `GHCR_NAMESPACE`
e `IMAGE_TAG` continuam selecionando as imagens; para baixar uma entrega do CI,
use `IMAGE_TAG=develop` ou `main`. Build local dispensa publicação no registry.

## Limites de recuperação

O backup é lógico e completo. Não inclui usuários/grants, binlogs, `.env`,
certificados ou configurações do host. Não há recuperação para instantes entre
dumps. Sob sucesso diário, a janela nominal de perda é de aproximadamente
24 horas; falhas podem ampliá-la. O tempo de recuperação precisa ser medido.

O bind mount sobrevive à troca do container, mas depende do disco e do host.
Não há cópia externa, criptografia, assinatura ou backup de arquivos externos
ao banco. Copie somente `.sql.gz` completos para armazenamento independente
conforme a operação do ambiente. Gzip valida compactação; exercícios periódicos
de restauração com arquivos reais validam a recuperação dos dados.
