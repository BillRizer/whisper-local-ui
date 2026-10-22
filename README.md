# Whisper Local
<img width="1536" height="932" alt="image" src="https://github.com/user-attachments/assets/955ebe3c-abc8-4dc6-a615-04b233be4d5d" />

Interface pequena para transcrever áudio e vídeo, gravar pelo microfone e traduzir fala para inglês usando modelos Whisper **no próprio computador**. Não usa a API da OpenAI nem exige chave. A primeira utilização de cada modelo baixa os pesos do Hugging Face; depois, os modelos em cache podem funcionar sem internet.

## Iniciar

Requer Python 3.10+ e um navegador recente. No Linux:

```bash
./run.sh
```

Abra **http://127.0.0.1:7860**. Para instalar manualmente ou em outros sistemas:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn whisper_ui.app:app --host 127.0.0.1 --port 7860
```

No Windows, ative o ambiente virtual com `.venv\Scripts\activate` e execute `python -m uvicorn whisper_ui.app:app --host 127.0.0.1 --port 7860`.

## Usar

1. Arraste até 20 arquivos de áudio ou vídeo, ou grave com o microfone.
2. Escolha **Transcrever** (idioma original) ou **Traduzir** (inglês).
3. Selecione idioma de entrada e modelo. O padrão **small** equilibra qualidade e velocidade; **large-v3** melhora a qualidade e precisa de mais memória. O primeiro download de **large-v3** tem cerca de 2,9 GB e pode levar alguns minutos; o andamento aparece no resultado.
4. Acompanhe a fila, copie o texto ou baixe TXT, SRT, VTT e JSON. **Baixar todos** cria um ZIP com todos os resultados concluídos.

Em **Modelo na memória**, use **Descarregar agora** para liberar os pesos do modelo carregado. Se houver trabalhos em andamento ou na fila, o descarregamento acontece depois deles. O seletor permite descarregar automaticamente após 1, 5, 10, 15, 30 ou 60 minutos de inatividade, ou escolher **Nunca**. O padrão é 15 minutos e a escolha fica salva em `data/settings.json`. A próxima transcrição carrega o modelo novamente do cache em disco, sem repetir o download. O contexto CUDA pode continuar ocupando uma pequena parte da VRAM mesmo após liberar os pesos.

Formatos aceitos: MP3, MP4, M4A, M4V, WAV, FLAC, OGG, OGA, OPUS, WEBM, MOV, MKV, AVI, AAC, AIFF, WMA, MPEG e MPGA. O arquivo precisa conter uma faixa de áudio decodificável. Cada arquivo pode ter até 1 GB. A gravação no navegador funciona em `localhost` e pede permissão para usar o microfone.

O processamento usa uma fila para manter a interface responsiva. Os arquivos enviados pelo navegador são apagados depois do processamento; arquivos locais indicados via MCP são preservados. Resultados concluídos ficam em `data/results/` para aparecer no histórico após reiniciar; podem ser removidos pela interface. O servidor aceita conexões apenas de `127.0.0.1` por padrão.

## Usar com Codex ou Claude Code (MCP)

Inicie `./run.sh` e deixe o servidor aberto. O mesmo processo atende a interface e o endpoint **Streamable HTTP** em `http://127.0.0.1:7860/mcp`, compartilhando fila, modelo e histórico. Registre o servidor no cliente local:

```bash
codex mcp add whisper-local --url http://127.0.0.1:7860/mcp
claude mcp add --transport http whisper-local http://127.0.0.1:7860/mcp
```

Esses comandos seguem as instruções oficiais de [Codex](https://developers.openai.com/learn/docs-mcp) e [Claude Code](https://code.claude.com/docs/en/mcp).

Se alterar `PORT`, substitua `7860` nos comandos. Os clientes precisam rodar no mesmo computador que o Whisper Local: as ferramentas recebem o **caminho absoluto** de um arquivo de áudio ou vídeo acessível ao servidor. Por exemplo, peça ao agente: “Transcreva `/home/usuario/Videos/reuniao.mp4` com o Whisper Local e resuma os pontos principais.” Nenhuma chave de API é necessária. O primeiro uso de um modelo ainda pode baixar seus pesos; a transcrição e a tradução são locais.

As ferramentas MCP são `transcribe_file` e `translate_file` (criam um trabalho), `get_job` e `wait_for_job` (acompanham o progresso), `read_transcript` (lê o texto em partes), `export_transcript` (salva TXT, SRT, VTT ou JSON em `data/exports/`), `list_jobs` (histórico), `get_model_status`, `unload_model` e `set_model_idle_timeout` (controle de memória). A tradução do Whisper gera texto em inglês. Arquivos enviados por caminho local permanecem no lugar mesmo após o trabalho ou o registro ser removido. Mantenha o servidor restrito a `127.0.0.1`, pois o MCP pode ler arquivos locais que o processo tenha permissão para acessar.

## GPU NVIDIA

O aplicativo escolhe CUDA automaticamente quando o CTranslate2 encontra uma GPU disponível; caso contrário, usa CPU e mostra isso no topo da interface. Para exigir GPU e receber um erro explícito se ela não estiver pronta:

```bash
WHISPER_DEVICE=cuda ./run.sh
```

É preciso ter driver NVIDIA funcional e as bibliotecas **CUDA 12 cuBLAS** e **cuDNN 9**, de acordo com a [documentação do faster-whisper](https://github.com/SYSTRAN/faster-whisper#gpu). O padrão na GPU é `float16` e na CPU é `int8`. Para reduzir consumo de VRAM:

```bash
WHISPER_COMPUTE_TYPE=int8_float16 WHISPER_DEVICE=cuda ./run.sh
```

O `run.sh` encontra automaticamente as bibliotecas CUDA instaladas pelo pip no ambiente virtual ou nos pacotes do usuário e as adiciona ao `LD_LIBRARY_PATH` antes de iniciar Python. Se `libcublas.so.12` ou `libcudnn.so.9` ainda não existirem, instale os pacotes no ambiente virtual:

```bash
.venv/bin/python -m pip install -r requirements-gpu.txt
./run.sh
```

Use `./run.sh` para iniciar a versão GPU no Linux; iniciar o `uvicorn` diretamente não configura o caminho dessas bibliotecas. O comando `nvidia-smi` deve funcionar antes de iniciar. Se CUDA não aparecer, confira driver e bibliotecas. Não há envio dos áudios para serviços externos; a conexão usada na primeira carga é apenas para baixar os pesos do modelo.

## Configuração

| Variável | Padrão | Uso |
| --- | --- | --- |
| `PORT` | `7860` | Porta local do servidor com `run.sh` |
| `WHISPER_DEVICE` | `auto` | `auto`, `cuda` ou `cpu` |
| `WHISPER_COMPUTE_TYPE` | `float16` na GPU, `int8` na CPU | Precisão e memória do CTranslate2 |
| `WHISPER_DATA_DIR` | `./data` | Pasta para arquivos temporários e histórico |
| `HF_HOME` | padrão do Hugging Face | Cache dos modelos |

Para executar os testes de API e exportação:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

## Referências

- [Whisper da OpenAI](https://openai.com/pt-BR/index/whisper/): reconhecimento multilíngue e tradução de fala para inglês.
- [Education-Victory/whisper-webui](https://github.com/Education-Victory/whisper-webui): inspiração para idioma opcional, contexto e formatos de exportação. Este projeto usa processamento local em vez da API.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): implementação local usada no processamento.
# whisper-local-ui
# whisper-local-ui
# whisper-local-ui
