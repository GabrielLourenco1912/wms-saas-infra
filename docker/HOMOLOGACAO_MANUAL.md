# Etapa manual final

Use o APK **profile** da branch `homol` (`mobile-homol-profile-apk` no CI),
instalado em Android físico. A API é `https://homol.api.wms.lourencogabriel.dev`
e o painel é `https://homol.wms.lourencogabriel.dev`. Dados e contas são
sintéticos. O protocolo está em
[tests/homol/manual-protocol.json](../tests/homol/manual-protocol.json).

As contas são `gestor@homol.wms.local` e `operador@homol.wms.local`. As senhas
preparadas para esta entrega estão em `.homol-private/deployment.json`, no
workspace local; não devem ir ao artigo ou aos artefatos. Para o código de login,
consulte o Mailpit por túnel SSH, conforme [HOMOLOGACAO.md](HOMOLOGACAO.md).

## 1. Captura e ciclo de vida

Imprima `artifacts/homol/manual/etiquetas-homologacao.pdf` em tamanho real.
No recebimento, abra **Conferir item** e experimente os botões de câmera nos
campos de produto, LPN e posição. O produto `HOMOL-TRACE` aceita o barcode
`000000000021`; a doca de entrada é `H-REC`.

Registre modelo, Android, versão/hash do APK, data e condições. Faça as seguintes
verificações, salvando fotos ou vídeo e o esperado/observado:

1. Autorizar a câmera e preencher o campo correto com uma etiqueta.
2. Cancelar a captura com texto anterior no campo: o texto deve permanecer.
3. Recusar a permissão e retornar à digitação; depois autorizar nas configurações.
4. Colocar o app em segundo plano durante a captura e retornar; fechar e reabrir.
5. Manter uma etiqueta enquadrada: uma abertura aceita um código, sem executar
   confirmação automática nem duplicar movimento.
6. Ler `000000000021` e conferir a preservação dos zeros iniciais.
7. Confirmar um código errado: a API deve rejeitar e o estoque deve permanecer.

O pré-recebimento inicial serve para demonstração. Para o ensaio repetido, crie
no painel um documento próprio de 100 unidades do produto HOMOL-TRACE. Informe
embalagem, quantidade de 1 unidade por confirmação, lote `MANUAL-2026`, validade
futura e LPN próprio na doca H-REC. O recebimento exige a leitura de SKU/barcode,
LPN e posição. Reutilizar um LPN só funciona enquanto ele estiver na mesma posição;
para outra execução, use documento/LPN novos. Os campos restantes devem estar
prontos antes da última leitura medida.

## 2. Feedback completo no telefone

No perfil, abra **Medições de homologação** e toque **Iniciar novo ensaio**.
O relógio começa no código decodificado ou no envio pelo teclado. Para digitação,
use a ação **Próximo/Concluir** do teclado no último campo de leitura. A espera até
tocar em confirmar faz parte da amostra. O relógio termina no primeiro quadro do
resultado confirmado ou rejeitado pelo servidor.

Colete por entrada (câmera e teclado) **20 confirmações e 10 rejeições**, mantendo
rede estável e registrando as operações realizadas. Para uma rejeição controlada,
leia um código de produto ou posição incorreto e confirme; depois corrija antes
da próxima tentativa. As rejeições não podem gerar saldo. Não misture pausa para
consultar instruções com uma medição que pretenda avaliar o fluxo contínuo.

Copie os resultados em **Copiar medições em CSV** e salve arquivos separados por
entrada/resultado. Registre todas as observações, inclusive as que excederem 2 s;
não elimine as lentas para melhorar o resultado. A aceitação é `< 2000 ms` por
amostra observada, com mediana, p95 e máximo e a quantidade de falhas. Os gráficos
do emulador no relatório automatizado são uma evidência complementar.

## 3. Fechamento documental

Acrescente os CSVs, fotos/vídeo e metadados ao diretório de evidências manual e
registre os resultados na revisão do TCC. A versão v3 já distingue câmera
implementada de captura física pendente; substitua essa pendência apenas com o
resultado observado. Se surgir defeito, descreva-o e mantenha o item aberto até
corrigir e repetir o cenário.

Luvas, compra de scanners, SDK de fabricante, piloto em empresa e acompanhamento
prolongado são trabalhos futuros da delimitação atual. Não são necessários para
este ensaio físico controlado de câmera e feedback.
