# Aceitação automatizada de homologação

Execute `bash tests/homol/run.sh` a partir da raiz, com emulador Android em
execução. Preparação, isolamento, portas, SMTP, métricas e ensaio manual estão em
[docker/HOMOLOGACAO.md](../../docker/HOMOLOGACAO.md).

- `acceptance.mjs`: coordena Playwright, Flutter e verificações do ciclo real.
- `api-scenarios.mjs`: rejeições e efeitos complementares via API real.
- `run-mobile.py`: executa o aplicativo em Android, com log privado sanitizado em
  caso de erro; o driver de teste reside no submódulo mobile.
- `performance-protocol.json`: carga e limites registrados antes do ensaio.
- `prepare-benchmark.mjs`: cria documentos novos fora da janela de medição.
- `waves.k6.js`: mede baseline e concorrência com dois operadores e um gestor.
- `analyze-benchmark.mjs`: exporta dados individuais e verifica reservas/demanda.
- `write-manifest.py`: registra revisões, ambiente e hashes das evidências.
- `report.py`: gera HTML portátil e CSV de feedback a partir das evidências
  sanitizadas; `--plots` acrescenta gráficos PNG/PDF com matplotlib.

Não use scraping como substituto de asserções: o Playwright interage com controles
reais, o Flutter percorre as telas e a API comprova estado e livro razão. A
câmera física e a ergonomia exigem ensaio manual separado. O teste não acessa
produção nem cria endpoints de bypass; planos com sessões ficam em
`.homol-private/`, fora dos artefatos publicados.
