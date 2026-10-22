"""Model loading, transcription, and subtitle export."""

from __future__ import annotations

import gc
import io
import os
import time
from pathlib import Path
from typing import Callable


MODELS = ("tiny", "base", "small", "medium", "large-v3")
MODEL_REPOS = {name: f"Systran/faster-whisper-{name}" for name in MODELS}
MODEL_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]
LANGUAGES = {
    "auto", "pt", "en", "es", "fr", "de", "it", "ja", "zh", "ko",
    "ru", "ar", "hi", "nl", "pl", "tr", "uk", "sv", "id", "vi",
}


def timestamp(seconds: float, separator: str = ",") -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}"


def render_result(result: dict, fmt: str) -> str:
    segments = result["segments"]
    if fmt == "txt":
        return result["text"].strip() + "\n"
    if fmt == "srt":
        return "\n".join(
            f"{index}\n{timestamp(segment['start'])} --> {timestamp(segment['end'])}\n"
            f"{segment['text'].strip()}\n"
            for index, segment in enumerate(segments, 1)
        )
    if fmt == "vtt":
        return "WEBVTT\n\n" + "\n".join(
            f"{timestamp(segment['start'], '.')} --> {timestamp(segment['end'], '.')}\n"
            f"{segment['text'].strip()}\n"
            for segment in segments
        )
    raise ValueError(f"Formato inválido: {fmt}")


def available_device() -> str:
    configured = os.getenv("WHISPER_DEVICE", "auto").lower()
    if configured in {"cpu", "cuda"}:
        return configured
    if configured != "auto":
        raise ValueError("WHISPER_DEVICE deve ser auto, cuda ou cpu")
    try:
        import ctranslate2

        return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
    except (ImportError, RuntimeError, OSError):
        return "cpu"


def _model_ready(path: str | Path) -> bool:
    folder = Path(path)
    return all((folder / name).is_file() for name in ("config.json", "model.bin", "tokenizer.json"))


def _format_bytes(value: float) -> str:
    units = ("B", "KB", "MB", "GB")
    for unit in units[:-1]:
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _download_model(name: str, progress: Callable[[float, str], None]) -> str:
    from huggingface_hub import snapshot_download
    from tqdm.auto import tqdm

    repo_id = MODEL_REPOS[name]
    try:
        cached = snapshot_download(repo_id, allow_patterns=MODEL_FILES, local_files_only=True)
        if _model_ready(cached):
            progress(0.24, f"Modelo {name} encontrado no cache.")
            return cached
    except Exception:
        pass  # Ausente no cache; o download a seguir mostra o erro de rede, se houver.

    progress(0.02, f"Conectando para baixar o modelo {name}…")

    class DownloadProgress(tqdm):
        def __init__(self, *args, **kwargs):
            self._is_transfer = kwargs.get("desc") == "Downloading bytes"
            self._last_report = 0.0
            kwargs["file"] = io.StringIO()
            kwargs["leave"] = False
            super().__init__(*args, **kwargs)

        def update(self, amount=1):
            result = super().update(amount)
            if self._is_transfer:
                current = time.monotonic()
                if current - self._last_report >= 0.35 or (self.total and self.n >= self.total):
                    self._last_report = current
                    fraction = min(1.0, self.n / self.total) if self.total else 0.0
                    detail = f"{_format_bytes(self.n)} / {_format_bytes(self.total)}" if self.total else _format_bytes(self.n)
                    progress(0.02 + 0.22 * fraction, f"Baixando {name}: {detail}")
            return result

    try:
        path = snapshot_download(repo_id, allow_patterns=MODEL_FILES, tqdm_class=DownloadProgress)
    except Exception as exc:
        raise RuntimeError(f"Falha ao baixar {name}. Verifique a conexão com o Hugging Face: {exc}") from exc
    if not _model_ready(path):
        raise RuntimeError(f"Download incompleto do modelo {name}. Tente novamente.")
    progress(0.24, f"Download de {name} concluído.")
    return path


class Transcriber:
    def __init__(self) -> None:
        self._model = None
        self._model_name: str | None = None
        self._device: str | None = None

    @property
    def loaded_model_name(self) -> str | None:
        return self._model_name if self._model is not None else None

    @property
    def loaded_device(self) -> str | None:
        return self._device if self._model is not None else None

    def unload_model(self) -> None:
        model = self._model
        if model is not None:
            model.model.unload_model()
        self._model = None
        self._model_name = None
        self._device = None
        if model is not None:
            del model
            gc.collect()

    def _get_model(self, name: str, progress: Callable[[float, str], None]):
        if self._model is not None and self._model_name == name:
            return self._model
        progress(0.01, f"Verificando modelo {name}…")
        from faster_whisper import WhisperModel

        self.unload_model()
        model_path = _download_model(name, progress)
        device = available_device()
        compute_type = os.getenv("WHISPER_COMPUTE_TYPE") or (
            "float16" if device == "cuda" else "int8"
        )
        progress(0.26, f"Inicializando {name} na {'GPU' if device == 'cuda' else 'CPU'}…")
        self._model = WhisperModel(model_path, device=device, compute_type=compute_type,
                                   local_files_only=True)
        self._model_name = name
        self._device = device
        return self._model

    def transcribe(
        self,
        path: str,
        *,
        model_name: str,
        task: str,
        language: str,
        prompt: str,
        progress: Callable[[float, str], None],
    ) -> dict:
        model = self._get_model(model_name, progress)
        progress(0.30, "Preparando áudio…")
        segments_iter, info = model.transcribe(
            path,
            task=task,
            language=None if language == "auto" else language,
            initial_prompt=prompt or None,
            vad_filter=True,
            beam_size=5,
        )
        duration = float(info.duration or 0)
        segments = []
        for segment in segments_iter:
            segments.append({
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "text": segment.text.strip(),
            })
            fraction = segment.end / duration if duration else 0
            progress(min(0.98, 0.32 + 0.66 * max(0.0, fraction)), "Processando fala…")
        text = " ".join(segment["text"] for segment in segments).strip()
        return {
            "text": text,
            "segments": segments,
            "duration": round(duration, 2),
            "detected_language": info.language,
            "device": self._device,
        }
