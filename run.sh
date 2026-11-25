#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

if ! .venv/bin/python -c 'import fastapi, faster_whisper, mcp, multipart, uvicorn' >/dev/null 2>&1; then
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
printf '\nWhisper Local: http://127.0.0.1:%s\n' "$app_port"
printf 'MCP: http://127.0.0.1:%s/mcp\n' "$app_port"
exec .venv/bin/python -m uvicorn whisper_ui.app:app --host 127.0.0.1 --port "$app_port"
