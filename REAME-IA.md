# Whisper Local — instruções para agentes de IA

## O que esta aplicação faz

Transcreve fala de arquivos de áudio ou vídeo para texto no idioma original e traduz fala para **inglês** com `faster-whisper`. Também permite gravar pelo microfone na interface web. O processamento ocorre no computador local, sem API externa ou chave; o primeiro uso de cada modelo pode baixar seus pesos do Hugging Face.

Há três formas de acesso ao mesmo servidor: interface web, API HTTP e ferramentas MCP. Todas compartilham a mesma fila de processamento, o modelo carregado e o histórico.

## Iniciar e localizar o servidor

Na raiz deste projeto, em Linux, execute:

```bash
rtk proxy ./run.sh
```

`run.sh` cria `.venv` e instala as dependências de `requirements.txt` quando necessário. Mantenha o processo aberto enquanto usar a UI ou o MCP. O servidor escuta apenas em `127.0.0.1`, na porta **7860** por padrão:

| Recurso | Endereço padrão |
| --- | --- |
| Interface web | `http://127.0.0.1:7860/` |
| MCP, transporte Streamable HTTP | `http://127.0.0.1:7860/mcp` |
| Estado do sistema | `http://127.0.0.1:7860/api/system` |
| Estado do modelo | `http://127.0.0.1:7860/api/model` |

Para mudar a porta, inicie com `rtk proxy env PORT=7861 ./run.sh` e use a nova porta em todos os endereços. Para conferir se o servidor responde:

```bash
rtk curl -sS http://127.0.0.1:7860/api/system
```

Neste workspace, `AGENTS.md` remete a `/home/odin/.codex/RTK.md`: agentes que executam comandos de shell devem usar o prefixo `rtk` (`rtk proxy` para comandos sem subcomando próprio). Fora deste ambiente, o comando de início é simplesmente `./run.sh`.

## Uso recomendado por uma IA: MCP

Conecte o cliente MCP ao endpoint `http://127.0.0.1:7860/mcp`. Exemplos de registro neste ambiente:

```bash
rtk proxy codex mcp add whisper-local --url http://127.0.0.1:7860/mcp
rtk proxy claude mcp add --transport http whisper-local http://127.0.0.1:7860/mcp
```

O cliente e o servidor precisam ter acesso ao **mesmo sistema de arquivos**: `transcribe_file` e `translate_file` recebem um caminho **absoluto**, legível pelo processo do servidor, como `/home/usuario/Videos/reuniao.mp4`. Um caminho que só existe em outro contêiner ou computador não funciona. O MCP não faz upload do arquivo.

Fluxo:

1. Chame `transcribe_file` para texto no idioma original ou `translate_file` para texto em inglês. Passe `path`; opcionalmente `language` (padrão `auto`), `model` (padrão `small`) e `prompt` (contexto ou vocabulário, até 1.000 caracteres). Guarde o `job_id` retornado.
2. Chame `wait_for_job(job_id, timeout_seconds=20)` até `status` ser `done` ou `error`. Cada chamada aceita no máximo 30 segundos. `get_job` fornece uma consulta imediata; `queued` e `running` ainda não são resultados finais. O primeiro download de um modelo pode demorar minutos; consulte `message` e `progress`.
3. Se `done`, chame `read_transcript(job_id)` para obter o texto. Para textos longos, repita com `start=next_start` até `next_start` ser `null`. O limite de `max_chars` é 12.000 por chamada.
4. Se precisar de arquivo, chame `export_transcript(job_id, format="txt")`. Os formatos são `txt`, `srt`, `vtt` e `json`; a ferramenta devolve o caminho absoluto do arquivo salvo em `data/exports/`.
5. Se `error`, leia o campo `error` de `get_job`/`wait_for_job` e reporte a falha. Não trate o trabalho como concluído.

Outras ferramentas: `list_jobs` lista o histórico; `get_model_status` informa o modelo carregado, dispositivo e tempo de descarregamento; `unload_model` libera o modelo da memória; `set_model_idle_timeout` configura o descarregamento automático (minutos: `0`, `1`, `5`, `10`, `15`, `30`, `60`; `0` desativa). Se houver trabalho ativo, o descarregamento espera a fila terminar. O próximo uso recarrega o modelo do cache.

Modelos disponíveis: `tiny`, `base`, `small`, `medium`, `large-v3`. Idiomas aceitos: `auto`, `pt`, `en`, `es`, `fr`, `de`, `it`, `ja`, `zh`, `ko`, `ru`, `ar`, `hi`, `nl`, `pl`, `tr`, `uk`, `sv`, `id`, `vi`. A tradução do Whisper é sempre **para inglês**, não para um idioma de destino arbitrário.

## UI e API HTTP

Na UI, é possível enviar até **20 arquivos por lote**, gravar pelo microfone, escolher tarefa/idioma/modelo, acompanhar a fila, copiar o resultado e baixar TXT, SRT, VTT ou JSON. O histórico fica na barra lateral. A gravação exige permissão de microfone no navegador e acesso por `localhost`.

Para integração sem MCP, `POST /api/jobs` aceita `multipart/form-data` com campo `files` (um ou mais arquivos) e campos opcionais `task=transcribe|translate`, `language=auto`, `model=small` e `prompt`. A resposta HTTP `202` contém trabalhos enfileirados. Use `GET /api/jobs/{job_id}` para consultar o resultado, `GET /api/jobs/{job_id}/download?format=txt` para baixar um resultado e `GET /api/export?format=txt` para baixar um ZIP dos resultados concluídos. `DELETE /api/jobs/{job_id}` remove um registro do histórico.

Extensões aceitas: MP3, MP4, M4A, M4V, WAV, FLAC, OGG, OGA, OPUS, WEBM, MOV, MKV, AVI, AAC, AIFF, WMA, MPEG e MPGA. O arquivo precisa conter áudio decodificável e ter até **1 GB**. A fila usa um trabalhador; vários trabalhos são processados em sequência.

## Particularidades operacionais

- **GPU:** `WHISPER_DEVICE=auto` usa CUDA quando disponível e CPU caso contrário. Para exigir CUDA, inicie com `rtk proxy env WHISPER_DEVICE=cuda ./run.sh`. Verifique o dispositivo em `/api/system` e o dispositivo efetivamente usado no resultado do trabalho.
- **Bibliotecas CUDA:** no Linux, prefira `run.sh`, que acrescenta ao `LD_LIBRARY_PATH` as bibliotecas CUDA instaladas pelo pip. Se aparecer `libcublas.so.12` ou `libcudnn.so.9` ausente, instale `requirements-gpu.txt` na `.venv` e reinicie pelo script: `rtk proxy .venv/bin/python -m pip install -r requirements-gpu.txt`. O driver NVIDIA também precisa estar funcional.
- **Modelos grandes:** `large-v3` baixa cerca de 2,9 GB no primeiro uso e usa mais memória. A etapa de download e inicialização pode ser longa; acompanhe `message`/`progress` do trabalho antes de concluir que travou.
- **Dados:** o padrão é `./data` (alterável por `WHISPER_DATA_DIR`). Resultados concluídos persistem em `data/results/`; configurações ficam em `data/settings.json`. Arquivos enviados pela UI são apagados após processamento. Arquivos fornecidos por caminho via MCP são preservados.
- **Rede:** o serviço fica restrito a `127.0.0.1` por padrão. Mantenha o MCP local, pois ele pode ler arquivos aos quais o processo tem acesso. Depois que os pesos estão em cache, a transcrição e a tradução funcionam sem conexão com serviços externos.

Para detalhes de instalação e uso humano, consulte [README.md](README.md).
