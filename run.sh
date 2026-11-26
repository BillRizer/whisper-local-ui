#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

if ! .venv/bin/python -c 'import av, fastapi, faster_whisper, mcp, multipart, uvicorn; assert 11 <= int(av.__version__.split(".")[0]) < 19' >/dev/null 2>&1; then
  if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
    printf 'pip não encontrado no ambiente virtual; tentando recuperá-lo com ensurepip.\n' >&2
    if ! .venv/bin/python -m ensurepip --upgrade; then
      printf 'Não foi possível recuperar o pip. Instale o suporte a venv/ensurepip do Python e tente novamente.\n' >&2
      exit 1
    fi
  fi
  .venv/bin/python -m pip install -r requirements.txt
fi

# Bibliotecas CUDA instaladas pelo pip ficam fora dos caminhos padrão do linker.
# Encontre pacotes no venv ou no site-packages do usuário antes de iniciar Python.
cuda_library_paths="$(.venv/bin/python - <<'PY'
from pathlib import Path
import site

roots = [*site.getsitepackages(), site.getusersitepackages()]
libraries = {"cublas": "libcublas.so.12", "cudnn": "libcudnn.so.9"}
paths = []
for package, filename in libraries.items():
    for root in roots:
        directory = Path(root) / "nvidia" / package / "lib"
        if (directory / filename).is_file():
            paths.append(str(directory))
            break
print(":".join(paths))
PY
)"
if [ -n "$cuda_library_paths" ]; then
  export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$cuda_library_paths"
fi

app_port="${PORT:-7860}"
app_host="${HOST:-127.0.0.1}"
display_host="$app_host"
if [ "$app_host" = "0.0.0.0" ]; then display_host="127.0.0.1"; fi
if [[ "$display_host" == *:* ]]; then display_host="[$display_host]"; fi
printf '\nWhisper Local: http://%s:%s\n' "$display_host" "$app_port"
printf 'MCP: http://%s:%s/mcp\n' "$display_host" "$app_port"
if [ "$app_host" != "127.0.0.1" ]; then
  printf 'Escutando em %s:%s. A API não exige autenticação; restrinja o acesso à rede.\n' "$app_host" "$app_port" >&2
  if [ "$app_host" = "0.0.0.0" ]; then
    printf 'Na rede local, acesse http://<IP-do-computador>:%s\n' "$app_port"
  fi
fi
exec .venv/bin/python -m uvicorn whisper_ui.app:app --host "$app_host" --port "$app_port"
