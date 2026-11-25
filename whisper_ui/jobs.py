"""Single-worker queue and local result history."""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .transcription import Transcriber


IDLE_UNLOAD_OPTIONS = (0, 1, 5, 10, 15, 30, 60)
DEFAULT_IDLE_UNLOAD_MINUTES = 15


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobManager:
    def __init__(self, data_dir: Path, transcriber: Transcriber | None = None) -> None:
        self.data_dir = data_dir
        self.upload_dir = data_dir / "uploads"
        self.result_dir = data_dir / "results"
        self.settings_path = data_dir / "settings.json"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.transcriber = transcriber or Transcriber()
        self.lock = threading.RLock()
        self.jobs: dict[str, dict] = {}
        self.pending: queue.Queue[tuple[str, str | None]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.active_job_id: str | None = None
        self.last_model_use: float | None = None
        self.unload_pending = False
        self.unload_error: str | None = None
        self.idle_unload_minutes = DEFAULT_IDLE_UNLOAD_MINUTES
        try:
            saved_minutes = json.loads(self.settings_path.read_text(encoding="utf-8"))["idle_unload_minutes"]
            if type(saved_minutes) is int and saved_minutes in IDLE_UNLOAD_OPTIONS:
                self.idle_unload_minutes = saved_minutes
        except (OSError, ValueError, KeyError, TypeError):
            pass
        for path in self.result_dir.glob("*.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if job["status"] == "done" and job["id"] == path.stem:
                    self.jobs[job["id"]] = job
            except (OSError, ValueError, KeyError):
                continue

    def start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        for path in self.upload_dir.iterdir():
            if path.is_file():
                path.unlink(missing_ok=True)
        self.worker = threading.Thread(target=self._run, daemon=True, name="whisper-worker")
        self.worker.start()

    def model_status(self) -> dict:
        with self.lock:
            loaded_model = self.transcriber.loaded_model_name
            busy = self.active_job_id is not None
            seconds_until_unload = None
            if (loaded_model and not busy and not self.unload_pending
                    and self.idle_unload_minutes and self.last_model_use is not None):
                seconds_until_unload = max(
                    0, round(self.idle_unload_minutes * 60 - (time.monotonic() - self.last_model_use))
                )
            return {
                "loaded_model": loaded_model,
                "device": self.transcriber.loaded_device,
                "busy": busy,
                "active_model": self.jobs[self.active_job_id]["model"] if busy else None,
                "unload_pending": self.unload_pending,
                "idle_unload_minutes": self.idle_unload_minutes,
                "seconds_until_unload": seconds_until_unload,
                "error": self.unload_error,
            }

    def set_idle_unload_minutes(self, minutes: int) -> dict:
        if type(minutes) is not int or minutes not in IDLE_UNLOAD_OPTIONS:
            raise ValueError(f"Escolha um destes intervalos: {', '.join(map(str, IDLE_UNLOAD_OPTIONS))}")
        with self.lock:
            temporary = self.settings_path.with_suffix(".tmp")
            temporary.write_text(json.dumps({"idle_unload_minutes": minutes}) + "\n", encoding="utf-8")
            temporary.replace(self.settings_path)
            self.idle_unload_minutes = minutes
            self.pending.put(("check_idle", None))
        return self.model_status()

    def request_model_unload(self) -> dict:
        with self.lock:
            if not self.unload_pending and (self.transcriber.loaded_model_name or self.active_job_id):
                self.unload_pending = True
                self.unload_error = None
                self.pending.put(("unload", None))
        return self.model_status()

    def submit(self, inputs: list[tuple[str, int, Path]], *, task: str, language: str,
               model: str, prompt: str, delete_inputs: bool = True) -> list[dict]:
        jobs = []
        with self.lock:
            for name, size, path in inputs:
                job = {
                    "id": path.stem if delete_inputs else uuid.uuid4().hex,
                    "name": name,
                    "size": size,
                    "task": task,
                    "language": language,
                    "model": model,
                    "prompt": prompt,
                    "status": "queued",
                    "message": "Na fila",
                    "progress": 0.0,
                    "created_at": now(),
                    "updated_at": now(),
                    "result": None,
                    "error": None,
                    "input_path": str(path),
                    "delete_input": delete_inputs,
                }
                self.jobs[job["id"]] = job
                jobs.append(self._public(job))
                self.pending.put(("job", job["id"]))
        return jobs

    @staticmethod
    def _public(job: dict, *, include_result: bool = False) -> dict:
        keys = ("id", "name", "size", "task", "language", "model", "status",
                "message", "progress", "created_at", "updated_at", "error")
        item = {key: job.get(key) for key in keys}
        if job.get("result"):
            item["duration"] = job["result"]["duration"]
            item["detected_language"] = job["result"]["detected_language"]
            item["device"] = job["result"]["device"]
            item["preview"] = job["result"]["text"][:200]
            if include_result:
                item["result"] = job["result"]
        return item

    def list(self) -> list[dict]:
        with self.lock:
            return [self._public(job) for job in sorted(
                self.jobs.values(), key=lambda job: job["created_at"], reverse=True
            )]

    def get(self, job_id: str) -> dict | None:
        with self.lock:
            job = self.jobs.get(job_id)
            return self._public(job, include_result=True) if job else None

    def remove(self, job_id: str) -> str:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return "missing"
            if job["status"] == "running":
                return "running"
            if job["status"] == "queued" and job.get("delete_input", False):
                path = Path(job["input_path"])
                path.unlink(missing_ok=True)
            (self.result_dir / f"{job_id}.json").unlink(missing_ok=True)
            del self.jobs[job_id]
            return "removed"

    def _update(self, job_id: str, **changes) -> None:
        with self.lock:
            job = self.jobs[job_id]
            job.update(changes, updated_at=now())

    def _unload_model(self) -> None:
        try:
            self.transcriber.unload_model()
        except Exception as exc:
            with self.lock:
                self.unload_error = str(exc) or type(exc).__name__
                self.last_model_use = time.monotonic()
        else:
            with self.lock:
                self.unload_error = None
                self.last_model_use = None
        finally:
            with self.lock:
                self.unload_pending = False

    def _maybe_unload_idle(self) -> None:
        with self.lock:
            if (not self.idle_unload_minutes or self.unload_pending or self.active_job_id
                    or not self.pending.empty() or not self.transcriber.loaded_model_name
                    or self.last_model_use is None):
                return
            if time.monotonic() - self.last_model_use < self.idle_unload_minutes * 60:
                return
            self.unload_pending = True
        self._unload_model()

    def _process_job(self, job_id: str) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            self.active_job_id = job_id
            self.unload_error = None
            job["status"] = "running"
            job["message"] = "Iniciando…"
            job["updated_at"] = now()
            arguments = {
                "path": job["input_path"],
                "model_name": job["model"],
                "task": job["task"],
                "language": job["language"],
                "prompt": job["prompt"],
            }
        try:
            result = self.transcriber.transcribe(
                **arguments,
                progress=lambda value, message: self._update(
                    job_id, progress=round(value, 3), message=message
                ),
            )
            with self.lock:
                stored = {key: value for key, value in self.jobs[job_id].items()
                          if key not in {"input_path", "prompt", "delete_input"}}
                stored.update(status="done", progress=1.0, message="Concluído",
                              result=result, updated_at=now())
            destination = self.result_dir / f"{job_id}.json"
            temporary = destination.with_suffix(".tmp")
            temporary.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
            temporary.replace(destination)
            self._update(job_id, status="done", progress=1.0,
                         message="Concluído", result=result)
        except Exception as exc:
            self._update(job_id, status="error", message="Falha no processamento",
                         error=str(exc) or type(exc).__name__)
        finally:
            if job["delete_input"]:
                Path(arguments["path"]).unlink(missing_ok=True)
            with self.lock:
                self.active_job_id = None
                if self.transcriber.loaded_model_name:
                    self.last_model_use = time.monotonic()

    def _run(self) -> None:
        while True:
            try:
                action, job_id = self.pending.get(timeout=1)
            except queue.Empty:
                self._maybe_unload_idle()
                continue
            try:
                if action == "job" and job_id is not None:
                    self._process_job(job_id)
                elif action == "unload":
                    self._unload_model()
                elif action == "check_idle":
                    self._maybe_unload_idle()
            finally:
                self.pending.task_done()


def new_upload_path(upload_dir: Path, extension: str) -> Path:
    return upload_dir / f"{uuid.uuid4().hex}{extension}"
