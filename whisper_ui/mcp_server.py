"""MCP tools backed by the same local queue as the browser UI."""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .jobs import JobManager
from .media import FORMATS, validate_local_file
from .transcription import LANGUAGES, MODELS, render_result


ModelName = Literal["tiny", "base", "small", "medium", "large-v3"]
LanguageCode = Literal[
    "auto", "pt", "en", "es", "fr", "de", "it", "ja", "zh", "ko",
    "ru", "ar", "hi", "nl", "pl", "tr", "uk", "sv", "id", "vi",
]
ExportFormat = Literal["txt", "srt", "vtt", "json"]
IdleUnloadMinutes = Literal[0, 1, 5, 10, 15, 30, 60]
MediaPath = Annotated[str, Field(description="Absolute path to an audio/video file on the server computer")]


def create_mcp_server(manager: JobManager) -> FastMCP:
    mcp = FastMCP(
        "Whisper Local",
        instructions=(
            "Transcribe or translate audio/video files on this computer using a local Whisper "
            "model. Submit an absolute file path, poll the job, then read the transcript in "
            "chunks or export it. Translation produces English text. No external transcription "
            "API is used. The first use of a model may download its weights."
        ),
        json_response=True,
    )

    def submit_file(path: str, task: str, language: str, model: str, prompt: str) -> dict:
        if language not in LANGUAGES:
            raise ValueError(f"Idioma inválido: {language}. Opções: {', '.join(sorted(LANGUAGES))}")
        if model not in MODELS:
            raise ValueError(f"Modelo inválido: {model}. Opções: {', '.join(MODELS)}")
        if len(prompt) > 1000:
            raise ValueError("Contexto muito longo (máximo de 1000 caracteres)")
        if importlib.util.find_spec("faster_whisper") is None:
            raise RuntimeError("Instale as dependências com pip install -r requirements.txt")
        media_path, size = validate_local_file(path)
        job = manager.submit(
            [(media_path.name, size, media_path)],
            task=task, language=language, model=model, prompt=prompt,
            delete_inputs=False,
        )[0]
        return {
            "job_id": job["id"],
            "status": job["status"],
            "message": "Use wait_for_job ou get_job para acompanhar o processamento.",
        }

    def summary(job_id: str) -> dict:
        job = manager.get(job_id)
        if job is None:
            raise ValueError(f"Trabalho não encontrado: {job_id}")
        job.pop("result", None)
        return job

    @mcp.tool()
    def transcribe_file(
        path: MediaPath,
        language: LanguageCode = "auto",
        model: ModelName = "small",
        prompt: Annotated[str, Field(description="Optional vocabulary or context, up to 1000 characters")] = "",
    ) -> dict:
        """Queue an audio/video file for speech-to-text in its original language. Path must be absolute and local to this server. Original file is preserved. Returns a job_id immediately."""
        return submit_file(path, "transcribe", language, model, prompt)

    @mcp.tool()
    def translate_file(
        path: MediaPath,
        language: LanguageCode = "auto",
        model: ModelName = "small",
        prompt: Annotated[str, Field(description="Optional vocabulary or context, up to 1000 characters")] = "",
    ) -> dict:
        """Queue an audio/video file for speech translation into English with local Whisper. Path must be absolute and local to this server. Original file is preserved. Returns a job_id immediately."""
        return submit_file(path, "translate", language, model, prompt)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_job(job_id: str) -> dict:
        """Get status, progress, error, and a short preview for a queued job. Does not return the full transcript."""
        return summary(job_id)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def wait_for_job(job_id: str, timeout_seconds: float = 20) -> dict:
        """Wait up to 30 seconds for a job, then return its current status. Repeat while queued/running; model downloads can take minutes."""
        if not 0 <= timeout_seconds <= 30:
            raise ValueError("timeout_seconds deve estar entre 0 e 30")
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while True:
            job = summary(job_id)
            if job["status"] in {"done", "error"} or asyncio.get_running_loop().time() >= deadline:
                return job
            await asyncio.sleep(min(0.25, deadline - asyncio.get_running_loop().time()))

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def read_transcript(job_id: str, start: int = 0, max_chars: int = 6000) -> dict:
        """Read a completed transcript in bounded character chunks. Pass next_start to the next call until it is null."""
        if start < 0:
            raise ValueError("start deve ser maior ou igual a zero")
        if not 1 <= max_chars <= 12000:
            raise ValueError("max_chars deve estar entre 1 e 12000")
        job = manager.get(job_id)
        if job is None:
            raise ValueError(f"Trabalho não encontrado: {job_id}")
        if job["status"] != "done":
            raise ValueError(f"Trabalho ainda não concluído: {job['status']}")
        transcript = job["result"]["text"]
        if start > len(transcript):
            raise ValueError("start ultrapassa o tamanho da transcrição")
        end = min(len(transcript), start + max_chars)
        return {
            "job_id": job_id,
            "text": transcript[start:end],
            "start": start,
            "next_start": end if end < len(transcript) else None,
            "total_chars": len(transcript),
            "detected_language": job["result"]["detected_language"],
        }

    @mcp.tool()
    def export_transcript(job_id: str, format: ExportFormat = "txt") -> dict:
        """Save a completed transcript as TXT, SRT, VTT, or JSON and return its absolute local path."""
        if format not in FORMATS:
            raise ValueError(f"Formato inválido: {format}. Opções: {', '.join(sorted(FORMATS))}")
        job = manager.get(job_id)
        if job is None:
            raise ValueError(f"Trabalho não encontrado: {job_id}")
        if job["status"] != "done":
            raise ValueError(f"Trabalho ainda não concluído: {job['status']}")
        export_dir = manager.data_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{Path(job['name']).stem}-{job_id[:8]}.{format}"
        path = export_dir / filename
        content = (json.dumps(job["result"], ensure_ascii=False, indent=2) + "\n"
                   if format == "json" else render_result(job["result"], format))
        path.write_text(content, encoding="utf-8")
        return {"job_id": job_id, "format": format, "path": str(path.resolve())}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def list_jobs(limit: int = 20) -> dict:
        """List recent local jobs with status and short previews. Returns at most 100 jobs."""
        if not 1 <= limit <= 100:
            raise ValueError("limit deve estar entre 1 e 100")
        return {"jobs": manager.list()[:limit]}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    def get_model_status() -> dict:
        """Check which Whisper model is loaded in RAM/VRAM, whether it is busy, and the idle unload setting."""
        return manager.model_status()

    @mcp.tool()
    def unload_model() -> dict:
        """Release the loaded Whisper model from RAM/VRAM. If a job is running, unload after queued jobs finish. A later job reloads it from the local cache."""
        return manager.request_model_unload()

    @mcp.tool()
    def set_model_idle_timeout(minutes: IdleUnloadMinutes) -> dict:
        """Persist automatic model unloading after this many idle minutes. Use 0 to disable automatic unloading."""
        return manager.set_idle_unload_minutes(minutes)

    return mcp
