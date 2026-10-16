# Concat pessoal

O editor é o Concat original. A personalização está inteiramente em `personal/`, fora dos arquivos do upstream. Fork: https://github.com/Kemuel-Batista/Concat. Original: https://github.com/jub0t/Concat.

## Abrir

No Windows, execute `Abrir-Concat-Pessoal.cmd`. Pelo WSL, na raiz do repositório:

```sh
bash personal/editor.sh
```

O comando abre o Concat em português e mantém a automação acompanhando importações. A janela do terminal mostra o andamento. Importe seu vídeo num projeto do Concat normalmente: após o salvamento automático, a automação lê a mídia importada e gera outro projeto em **Vídeos/Concat-Pessoal**. Ele aparece em **Recentes**; abra-o para revisar suas três timelines:

1. **Original**, no tamanho e na taxa da gravação.
2. **Aula editada**, com pausas encurtadas, cortes editáveis e legendas nativas.
3. **Vertical**, em 1080×1920, com cortes e legendas correspondentes.

O Concat protege o projeto aberto na janela contra edição pela API. A automação respeita esse bloqueio: lê o manifesto salvo para descobrir importações e monta um projeto separado pela API oficial. Não escreve no manifesto que você está editando. Cada vídeo com áudio do projeto importado recebe seu próprio resultado. O monitor lembra os projetos de entrada mesmo quando eles saem da lista de recentes; execuções manuais e automáticas compartilham uma trava para não processar o mesmo cache simultaneamente. Resultados gerados são identificados para não serem processados novamente.

As timelines continuam apontando para o vídeo original. Nenhum MP4 intermediário é necessário para os cortes, as legendas ou o enquadramento; a entrega final usa o exportador do Concat. A saída de Premiere é um XML Final Cut Pro 7 com os cortes e um SRT, ambos editáveis. `resultado.json` informa as decisões e os itens para conferir.

## Os cinco pacotes

Os ZIPs fornecidos são extraídos **sem alteração** em `personal/.local/skills/`. `skills.lock.json` registra SHA-256 de cada pacote e arquivo. Essa cópia local não é publicada no fork; os scripts permanecem acompanhados da identificação e das skills de Sérgio Rossi/OnTime Vídeos.

| Pacote | Uso no editor pessoal |
| --- | --- |
| corte-de-pausas | Transcrição com palavras e análise real de silêncio; plano convertido em trechos na timeline. |
| legenda-no-tempo | Reutiliza a mesma transcrição e remapeia as legendas ao tempo editado; texto nativo na timeline e SRT. |
| video-vertical | Quadro-guia e posição do rosto; o recorte vira uma propriedade editável do Concat. |
| projeto-premiere | XML vertical e SRT com referência ao arquivo bruto; caminhos Windows normalizados. |
| imagem-por-frase | Busca no Pixabay, planejamento pelo contexto com Codex e escolha visual das miniaturas antes de inserir imagens. |

O adaptador conserva palavras que o algoritmo classificou apenas como prefixo travado sem hífen. Retomadas e remoções pouco seguras ficam no relatório para revisão. Os cortes têm transição visual e rampas curtas no áudio; as legendas acompanham os mesmos intervalos. Se o detector não conseguir localizar o rosto de forma estável, a versão vertical preserva a imagem completa e pede revisão do enquadramento, evitando escolher um rosto inexistente.

### Imagens por frase

Guarde sua chave do Pixabay em `~/.pixabay_key` ou na variável `PIXABAY_API_KEY`, sem publicá-la no Git. O Codex deve estar autenticado. A automação envia o texto reconhecido e as miniaturas ao planejador para avaliar contexto e escolha visual; não envia o vídeo completo. Não baixa imagens quando a configuração está ausente: o resultado informa essa pendência, enquanto as outras saídas ficam prontas.

Após configurar, reprocesse para gerar uma nova versão sem sobrescrever suas edições:

```sh
personal/.venv/bin/python personal/run.py process "/caminho/da/aula.mp4" --force
```

## Comandos úteis

```sh
personal/.venv/bin/python personal/run.py doctor
personal/.venv/bin/python personal/run.py status
personal/.venv/bin/python personal/run.py process "/caminho/da/aula.mp4"
personal/.venv/bin/python -m unittest discover -s personal/tests -v
```

`--words transcricao.json` aceita palavras reais com tempos (`w/ini/fim` ou `text/start/end`). Os tempos são validados antes do processamento. `--force` cria outra versão. Falhas e interrupções ficam registradas em `personal/.local/jobs.sqlite`; o cache de transcrição pode ser reaproveitado na retomada. Processamentos falhos não ficam repetindo indefinidamente: o comando `process` permite retomar após corrigir a causa.

## Receber atualizações

O remoto `origin` aponta para seu fork, e `upstream`, para `jub0t/Concat`. A branch `personal/automation` contém apenas arquivos novos em `personal/`. O commit base está em `upstream.lock.json`.

```sh
# Baixa as referências e mostra os commits novos, sem alterar seu editor.
personal/.venv/bin/python personal/update.py check

# Testa o merge num worktree separado, o contrato e os adaptadores.
personal/.venv/bin/python personal/update.py validate

# Com Rust e as bibliotecas do upstream instalados, compila e testa também.
personal/.venv/bin/python personal/update.py validate --native

# Aplica apenas depois da validação nativa bem-sucedida.
personal/.venv/bin/python personal/update.py apply --native
```

Issues e PRs entram quando são incorporados ao upstream. Não aplicamos PRs abertos automaticamente. A validação Python confere o contrato e a camada pessoal; ela não substitui compilar e testar o novo editor. Atualizar o código-fonte não substitui o binário instalado: para usar uma nova versão, instale a release verificada ou compile o commit validado, atualize `config.local.json` e execute `doctor`/`verify_runtime.py` com uma amostra.

## Ambiente local

A instalação desta máquina usa o binário **Windows 0.2.7**, extraído da distribuição oficial e conferido com o `SHA256SUMS` da release. Os scripts rodam no WSL e conversam com a API Windows por um canal autenticado local. A versão Linux foi testada neste WSL e encerrou com falha de inicialização; não foi alterada para contornar isso.

O programa de edição não foi recompilado nesta instalação. O teste nativo utilizou a release oficial; validar outro commit Rust exige a toolchain documentada pelo Concat. Credenciais, caminhos locais, runtime e mídia ficam em `.local/` e `config.local.json`, ignorados pelo Git. `config.json` contém apenas os padrões compartilháveis. O projeto anterior foi arquivado fora desta pasta; sua localização está em `.local/migration.json`.

Para reinstalar os pacotes e as dependências desta camada:

```sh
python3 -m venv personal/.venv
personal/.venv/bin/python -m pip install -r personal/requirements.txt
personal/.venv/bin/python personal/run.py install-skills "/pasta/dos/cinco/zips"
```

FFmpeg e FFprobe devem estar no PATH ou em `personal/.local/tools/bin`. A configuração local registra o executável oficial, a pasta `portable` e o diretório de projetos; a API deve estar ativa no endereço configurado. Use `doctor` antes de processar.

## Validação desta entrega

O teste de importação usou 12,084 segundos reais da aula, com transcrição local, análise dos scripts e montagem pela API do Concat Windows 0.2.7. O resultado teve três timelines, três trechos de vídeo e dez legendas editáveis, com duração editada de 11,5 segundos. Uma prévia nativa foi inspecionada para confirmar a legenda sobre a imagem. O manifesto de entrada permaneceu idêntico. Nove testes automatizados verificam os cuidados de fala, tempos, caminhos, monitor e contrato; a verificação nativa está em `verify_runtime.py`.

Imagens por frase ainda dependem da chave Pixabay e não foram validadas com downloads reais nesta instalação. No trecho de aula, o rosto pequeno da webcam não foi encontrado com estabilidade: a timeline vertical preservou o quadro inteiro para revisão. Não houve renderização completa de MP4 nem recompilação do Rust.
