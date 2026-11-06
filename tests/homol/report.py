#!/usr/bin/env python3
"""Build a portable evidence report from sanitized outputs, never private plans."""
import argparse
import base64
import csv
import html
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('directory', type=Path)
parser.add_argument('--plots', action='store_true', help='Also requires matplotlib')
args = parser.parse_args()
out = args.directory

def read(name, fallback=None):
    path = out / name
    return json.loads(path.read_text()) if path.exists() else fallback

def esc(value):
    return html.escape(str(value))

def table(headers, rows):
    return '<table><thead><tr>' + ''.join('<th>' + esc(h) + '</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + esc(c) + '</td>' for c in row) + '</tr>' for row in rows) + '</tbody></table>'

acceptance = read('acceptance-results.json', [])
mobile = read('mobile-results.json', {})
benchmark = read('benchmark-results.json', {})
manifest = read('manifest.json', {})
samples = mobile.get('feedbackSamples', [])
with (out / 'mobile-feedback.csv').open('w', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(['input', 'outcome', 'duration_ms'])
    writer.writerows((s['input'], s['outcome'], s['durationMs']) for s in samples)

benchmark_rows = []
criteria = []
for phase, metrics in benchmark.get('summaries', {}).items():
    for name, metric_data in metrics.items():
        for expression, status in metric_data.get('thresholds', {}).items():
            criteria.append([phase, name, expression, 'Aprovado' if status['ok'] else 'REPROVADO'])
    for metric in ['wave_generation_ms', 'receipt_confirmation_ms']:
        if metric in metrics:
            values = metrics[metric]['values']
            benchmark_rows.append([phase, metric, *[f'{values[key]:.2f}' for key in ['med', 'p(95)', 'max']]])
for phase, metrics in benchmark.get('summaries', {}).items():
    for metric in sorted(metrics):
        if metric.startswith('wave_generation_ms{'):
            values = metrics[metric]['values']
            benchmark_rows.append([phase, metric, *[f'{values[key]:.2f}' for key in ['med', 'p(95)', 'max']]])

if args.plots and benchmark:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.size': 9, 'axes.spines.top': False, 'axes.spines.right': False})
    with (out / 'benchmark-samples.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 3.5))
    for ax, metric, groups, labels, limit, title in [
        (axes[0], 'wave_generation_ms', ['10', '50', '200'], ['10', '50', '200'], 5000, 'Geração de ondas (n = 10 por tamanho)'),
        (axes[1], 'receipt_confirmation_ms', ['baseline', 'concurrent'], ['Sem ondas', 'Com ondas'], 2000, 'Confirmação HTTP (n = 60 por fase)'),
    ]:
        values = [[float(row['duration_ms']) for row in rows if row['metric'] == metric and (row['orders'] if metric.startswith('wave') else row['phase']) == group] for group in groups]
        ax.boxplot(values, tick_labels=labels, showfliers=False, widths=.48)
        for index, group in enumerate(values, 1):
            ax.scatter(np.linspace(index-.13, index+.13, len(group)), group, s=9, color='#245a76', alpha=.7)
        ax.axhline(limit, color='#a13624', linestyle='--', label=f'Critério p95 < {limit/1000:g} s')
        ax.set(title=title, ylabel='Duração (ms)', xlabel='Pedidos por onda' if metric.startswith('wave') else 'Dois operadores distintos')
        ax.set_ylim(bottom=0)
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('Carga sintética controlada · API e MySQL isolados', fontsize=11)
    fig.tight_layout()
    for suffix in ['png', 'pdf']:
        fig.savefig(out / f'desempenho.{suffix}', dpi=220, bbox_inches='tight')
    plt.close(fig)
    if samples:
        fig, ax = plt.subplots(figsize=(6.8, 2.7))
        ax.bar(range(1, len(samples)+1), [s['durationMs'] for s in samples], color='#245a76')
        ax.axhline(2000, color='#a13624', linestyle='--', label='RNF004: feedback < 2 s')
        ax.set(xlabel='Amostra do ciclo automatizado', ylabel='Código → feedback (ms)', title='Android emulado · digitação · build debug')
        ax.set_xticks(range(1, len(samples)+1))
        ax.legend(fontsize=8)
        fig.tight_layout()
        for suffix in ['png', 'pdf']:
            fig.savefig(out / f'feedback-emulador.{suffix}', dpi=220, bbox_inches='tight')
        plt.close(fig)

sections = [
    '<h1>WMS · Evidências de homologação</h1>',
    '<p>Dados sintéticos. Testes de interface, API e desempenho têm escopos distintos. A câmera física, o feedback em aparelho e a ergonomia dependem do ensaio manual.</p>',
    '<h2>Revisões e ambiente</h2>',
    table(['Componente', 'Commit'], manifest.get('revisions', {}).items()),
    '<p>' + esc(manifest.get('system', '')) + ' · CPUs do host: ' + esc(manifest.get('cpuCount', '')) + '</p>',
    '<h2>Aceitação</h2>',
    table(['Cenário', 'Resultado'], [[r['name'], r['status']] for r in acceptance]),
    '<h2>Desempenho</h2>',
    '<p>30 ondas (10/50/200 pedidos, dez repetições), 60 recebimentos por fase. Critérios: p95 de onda &lt; 5 s; p95 HTTP &lt; 2 s; 100% dos comandos aprovados. Tempos de HTTP não comprovam o feedback completo da interface.</p>',
    table(['Fase', 'Métrica', 'Mediana (ms)', 'p95 (ms)', 'Máximo (ms)'], benchmark_rows),
    table(['Fase', 'Métrica', 'Critério', 'Resultado'], criteria),
    '<h2>Feedback observado no emulador</h2>',
    table(['Entrada', 'Resultado', 'Duração (ms)'], [[s['input'], s['outcome'], f"{s['durationMs']:.3f}"] for s in samples]),
    '<p>O tempo começa na última leitura completa e inclui a espera até confirmar o formulário. O grupo automatizado utiliza digitação; não comprova decodificação óptica nem desempenho de um telefone físico.</p>',
]
for path in sorted(out.glob('*.png')):
    encoded = base64.b64encode(path.read_bytes()).decode()
    sections.append('<figure><img alt="' + esc(path.stem) + '" src="data:image/png;base64,' + encoded + '"><figcaption>' + esc(path.name) + '</figcaption></figure>')
sections.extend([
    '<h2>Limites</h2><p>Carga sintética, um item por pedido, uma topologia e fases sequenciais com histórico acumulado. Os percentis descrevem a amostra observada. Não demonstram disponibilidade prolongada, capacidade de produção, uso com luvas ou periféricos.</p>',
    '<h2>Arquivos verificáveis</h2>',
    table(['Arquivo', 'SHA-256'], manifest.get('artifactsSha256', {}).items()),
])
style = 'body{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#152b39}h1,h2{line-height:1.2}h2{margin-top:36px}table{border-collapse:collapse;width:100%;font-size:14px;margin:16px 0}th,td{text-align:left;border-bottom:1px solid #d5dfe4;padding:8px;overflow-wrap:anywhere}th{background:#edf3f6}figure{margin:28px 0;padding:16px;background:#f3f6f8}img{max-width:100%;height:auto;max-height:750px;display:block;margin:auto}figcaption{margin-top:8px;color:#50646f} @media print{body{margin:0}figure,table{break-inside:avoid}}'
(out / 'relatorio.html').write_text('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WMS · Homologação</title><style>' + style + '</style><body>' + '\n'.join(sections) + '</body></html>')
print('Relatório portátil e CSV gerados; somente evidências sanitizadas foram lidas.')
