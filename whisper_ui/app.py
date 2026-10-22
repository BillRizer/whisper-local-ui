"""FastAPI routes for the local Whisper interface."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from .jobs import JobManager, new_upload_path
from .mcp_server import create_mcp_server
from .media import ALLOWED_EXTENSIONS, FORMATS, MAX_FILE_BYTES, MAX_FILES
from .transcription import LANGUAGES, MODELS, available_device, render_result


ROOT = Path(__file__).resolve().parent.parent


class ModelSettings(BaseModel):
    idle_unload_minutes: int


def save_upload(source, path: Path, name: str) -> int:
    total = 0
    with path.open("wb") as target:
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise HTTPException(413, f"Arquivo maior que 1 GB: {name}")
            target.write(chunk)
    if total == 0:
        raise HTTPException(400, f"Arquivo vazio: {name}")
    return total


def create_app(data_dir: Path | None = None, manager: JobManager | None = None) -> FastAPI:
    data_dir = data_dir or Path(os.getenv("WHISPER_DATA_DIR", ROOT / "data"))
    manager = manager or JobManager(data_dir)
    mcp = create_mcp_server(manager)
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager.start()
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Whisper Local", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.manager = manager
    app.state.mcp = mcp
    @app.get("/")
    async def home():
        return Response(content=(ROOT / "static" / "index.html").read_bytes(), media_type="text/html")

    @app.get("/static/{filename}")
    async def static_file(filename: str):
        media_types = {"app.js": "application/javascript", "styles.css": "text/css",
                       "favicon.svg": "image/svg+xml"}
        if filename not in media_types:
            raise HTTPException(404, "Arquivo não encontrado")
        return Response(content=(ROOT / "static" / filename).read_bytes(),
                        media_type=media_types[filename])

    @app.get("/api/system")
    async def system():
        installed = importlib.util.find_spec("faster_whisper") is not None
        return {
            "engine_installed": installed,
            "device": available_device() if installed else "unknown",
            "models": MODELS,
            "max_files": MAX_FILES,
            "max_file_bytes": MAX_FILE_BYTES,
        }

    @app.get("/api/model")
    async def model_status():
        return manager.model_status()

    @app.put("/api/model/settings")
    async def save_model_settings(settings: ModelSettings):
        try:
            return manager.set_idle_unload_minutes(settings.idle_unload_minutes)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/model/unload", status_code=202)
    async def unload_model():
        return manager.request_model_unload()

    @app.get("/api/jobs")
    async def list_jobs():
        return manager.list()

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str):
        job = manager.get(job_id)
        if not job:
            raise HTTPException(404, "Resultado não encontrado")
        return job

    @app.post("/api/jobs", status_code=202)
    async def create_jobs(
        files: list[UploadFile] = File(...),
        task: str = Form("transcribe"),
        language: str = Form("auto"),
        model: str = Form("small"),
        prompt: str = Form(""),
    ):
        if task not in {"transcribe", "translate"}:
            raise HTTPException(400, "Tarefa inválida")
        if language not in LANGUAGES:
            raise HTTPException(400, "Idioma inválido")
        if model not in MODELS:
            raise HTTPException(400, "Modelo inválido")
        if len(prompt) > 1000:
            raise HTTPException(400, "Contexto muito longo (máximo de 1000 caracteres)")
        if not 1 <= len(files) <= MAX_FILES:
            raise HTTPException(400, f"Selecione de 1 a {MAX_FILES} arquivos")
        if importlib.util.find_spec("faster_whisper") is None:
            raise HTTPException(503, "Instale as dependências com pip install -r requirements.txt")
        inputs = []
        try:
            for upload in files:
                name = (upload.filename or "arquivo").replace("\\", "/").split("/")[-1]
                extension = Path(name).suffix.lower()
                if extension not in ALLOWED_EXTENSIONS:
                    raise HTTPException(400, f"Formato não aceito: {name}")
                path = new_upload_path(manager.upload_dir, extension)
                inputs.append((name, 0, path))
                total = save_upload(upload.file, path, name)
                inputs[-1] = (name, total, path)
        except Exception:
            for _, _, path in inputs:
                path.unlink(missing_ok=True)
            raise
        return manager.submit(inputs, task=task, language=language, model=model, prompt=prompt)

    @app.delete("/api/jobs/{job_id}", status_code=204)
    async def delete_job(job_id: str):
        outcome = manager.remove(job_id)
        if outcome == "missing":
            raise HTTPException(404, "Resultado não encontrado")
        if outcome == "running":
            raise HTTPException(409, "Aguarde o processamento terminar")
        return Response(status_code=204)

    @app.get("/api/jobs/{job_id}/download")
    async def download(job_id: str, format: str = "txt"):
        if format not in FORMATS:
            raise HTTPException(400, "Formato de exportação inválido")
        job = manager.get(job_id)
        if not job or job["status"] != "done":
            raise HTTPException(404, "Resultado não encontrado")
        content = (json.dumps(job["result"], ensure_ascii=False, indent=2) + "\n"
                   if format == "json" else render_result(job["result"], format))
        stem = Path(job["name"]).stem or "transcricao"
        filename = f"{stem}.{format}"
        media_type = "application/json" if format == "json" else "text/plain; charset=utf-8"
        return Response(content=content, media_type=media_type, headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        })

    @app.get("/api/export")
    async def export_all(format: str = "txt"):
        if format not in FORMATS:
            raise HTTPException(400, "Formato de exportação inválido")
        completed = [manager.get(job["id"]) for job in manager.list() if job["status"] == "done"]
        if not completed:
            raise HTTPException(404, "Nenhum resultado concluído")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for job in completed:
                content = (json.dumps(job["result"], ensure_ascii=False, indent=2) + "\n"
                           if format == "json" else render_result(job["result"], format))
                archive.writestr(f"{Path(job['name']).stem}-{job['id'][:8]}.{format}", content)
        return Response(content=output.getvalue(), media_type="application/zip", headers={
            "Content-Disposition": "attachment; filename=whisper-resultados.zip"
        })

    # Keep the specific UI/API routes first; this mount serves /mcp.
    app.mount("/", mcp_app)
    return app


app = create_app()
