# Validação do backup WMS — 30/10/2026

Foi executado `bash docker/mysql-backup/tests/integration.sh` com código de
saída zero, usando a imagem construída de `docker/mysql-backup`, MySQL 8.0
em tmpfs e credenciais geradas para um projeto Compose descartável.
O `.env` da aplicação, seu volume `db_data` e o banco operacional não foram usados.

Foram verificados:

- Serviço de backup habilitado no Compose padrão, com imagem GHCR e sem profile.
- Validação de configuração com MySQL ainda desligado; recusa de senha ausente,
  porta inválida e retenção inferior a 30 dias.
- Nome UTC com sufixo aleatório, diretório `0700`, arquivos `0600` e gzip íntegro.
- Retenção de 30/45 dias, preservação de arquivos recentes ou alheios ao padrão
  e preservação de backups vencidos quando um dump falha.
- Trava entre containers para backup/restauração e liberação após saída do dono.
- Recusa de destinos operacional, de sistema, inexistente, inválido ou ocupado
  por tabelas, rotinas ou eventos; recusa de gzip corrompido e SQL com `USE`.
- Bloqueio de restauração com event scheduler ativo; restauração de UTF-8,
  tabelas, view, função, procedure, evento e gatilho executado de fato.
- Aviso de importação parcial e recusa de nova importação no destino ocupado.
- Aplicação das migrations reais V1/V2 do WMS em banco de teste, backup e
  recuperação de tabelas, dois perfis iniciais, armazém com texto UTF-8 e
  gatilho que bloqueia exclusão após restauração.
- Cron real disparando um backup com filesystem da imagem somente para leitura,
  fuso do host e configuração herdada do ambiente inicial do container; a agenda
  de teste roda por minuto e a agenda de produção foi conferida como `15 2`.
- Senha com caracteres especiais, ausência de credenciais nos logs capturados
  e limpeza de temporários e arquivos parciais.

A suíte remove seus containers, rede, imagem e arquivos ao terminar, inclusive
arquivos pertencentes ao root do container quando o executor não é root.

Esse resultado comprova os cenários de integração descritos. Não comprova
implantação, publicação no GHCR, operação diária em produção, observação por
30 dias, cópia externa, tempo de recuperação ou recuperação de um backup real
do ambiente operacional.
