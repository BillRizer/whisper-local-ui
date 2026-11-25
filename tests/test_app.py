import asyncio
import io
import json
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from whisper_ui.app import create_app
from whisper_ui.jobs import JobManager
from whisper_ui.transcription import Transcriber, _download_model, render_result, timestamp


class FakeTranscriber:
    loaded_model_name = None
    loaded_device = None

    def transcribe(self, path, *, model_name, task, language, prompt, progress):
        assert Path(path).read_bytes() == b"test-audio"
        self.loaded_model_name = model_name
        self.loaded_device = "cuda"
        progress(0.5, "Processando fala…")
        return {
            "text": "Olá, mundo.",
            "segments": [{"start": 0.0, "end": 1.25, "text": "Olá, mundo."}],
            "duration": 1.25,
            "detected_language": "pt",
            "device": "cuda",
        }

    def unload_model(self):
        self.loaded_model_name = None
        self.loaded_device = None


class FormatTests(unittest.TestCase):
    def test_subtitles_and_text(self):
        result = {
            "text": "Olá, mundo.",
            "segments": [{"start": 0, "end": 1.25, "text": "Olá, mundo."}],
        }
        self.assertEqual(timestamp(3661.234), "01:01:01,234")
        self.assertIn("00:00:01,250", render_result(result, "srt"))
        self.assertIn("00:00:01.250", render_result(result, "vtt"))
        self.assertEqual(render_result(result, "txt"), "Olá, mundo.\n")


class ModelDownloadTests(unittest.TestCase):
    def test_download_reports_bytes_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for filename in ("config.json", "model.bin", "tokenizer.json"):
                (folder / filename).write_bytes(b"ready")
            messages = []
            calls = []

            def fake_snapshot(repo_id, **kwargs):
                calls.append(kwargs)
                if kwargs.get("local_files_only") and len(calls) == 1:
                    raise FileNotFoundError("uncached")
                if "tqdm_class" in kwargs:
                    with kwargs["tqdm_class"](desc="Downloading bytes", total=2048) as bar:
                        bar.update(1024)
                        bar.update(1024)
                return str(folder)

            with patch("huggingface_hub.snapshot_download", side_effect=fake_snapshot):
                self.assertEqual(_download_model("large-v3", lambda value, text: messages.append((value, text))), str(folder))
                self.assertEqual(_download_model("large-v3", lambda value, text: messages.append((value, text))), str(folder))
            self.assertEqual(len(calls), 3)
            self.assertTrue(any("Baixando large-v3:" in text for _, text in messages))
            self.assertTrue(any("cache" in text for _, text in messages))

    def test_unload_releases_backend_and_clears_state(self):
        transcriber = Transcriber()
        backend = Mock()
        transcriber._model = SimpleNamespace(model=backend)
        transcriber._model_name = "small"
        transcriber._device = "cuda"
        transcriber.unload_model()
        backend.unload_model.assert_called_once_with()
        self.assertIsNone(transcriber.loaded_model_name)
        self.assertIsNone(transcriber.loaded_device)

    def test_unloaded_model_is_created_again_on_next_use(self):
        transcriber = Transcriber()
        created = []
        fake_module = ModuleType("faster_whisper")

        def fake_model(*args, **kwargs):
            wrapper = SimpleNamespace(model=Mock())
            created.append(wrapper)
            return wrapper

        fake_module.WhisperModel = fake_model
        with patch.dict(sys.modules, {"faster_whisper": fake_module}), \
                patch("whisper_ui.transcription._download_model", return_value="/cache/small"), \
                patch("whisper_ui.transcription.available_device", return_value="cpu"):
            first = transcriber._get_model("small", lambda *_: None)
            transcriber.unload_model()
            second = transcriber._get_model("small", lambda *_: None)
        self.assertIsNot(first, second)
        self.assertEqual(len(created), 2)
        first.model.unload_model.assert_called_once_with()


class ModelLifecycleTests(unittest.TestCase):
    def test_manual_unload_and_idle_timeout_reload_on_next_job(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "audio.mp3"
            source.write_bytes(b"test-audio")
            manager = JobManager(folder, FakeTranscriber())
            manager.start()

            def submit_and_wait():
                job_id = manager.submit([(source.name, source.stat().st_size, source)],
                                        task="transcribe", language="auto", model="small",
                                        prompt="", delete_inputs=False)[0]["id"]
                manager.pending.join()
                self.assertEqual(manager.get(job_id)["status"], "done")
                return job_id

            submit_and_wait()
            self.assertEqual(manager.model_status()["loaded_model"], "small")
            manager.request_model_unload()
            manager.pending.join()
            self.assertIsNone(manager.model_status()["loaded_model"])
            self.assertEqual(source.read_bytes(), b"test-audio")

            submit_and_wait()
            self.assertEqual(manager.model_status()["loaded_model"], "small")
            with manager.lock:
                manager.last_model_use = time.monotonic() - 61
            manager.set_idle_unload_minutes(1)
            manager.pending.join()
            self.assertIsNone(manager.model_status()["loaded_model"])
            self.assertEqual(JobManager(folder, FakeTranscriber()).idle_unload_minutes, 1)
            submit_and_wait()
            self.assertEqual(manager.model_status()["loaded_model"], "small")

    def test_unload_waits_for_running_job(self):
        class SlowTranscriber(FakeTranscriber):
            def __init__(self):
                self.started = threading.Event()
                self.release = threading.Event()

            def transcribe(self, *args, **kwargs):
                self.started.set()
                if not self.release.wait(5):
                    raise TimeoutError("Teste excedeu o prazo")
                return super().transcribe(*args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "audio.mp3"
            source.write_bytes(b"test-audio")
            transcriber = SlowTranscriber()
            manager = JobManager(folder, transcriber)
            manager.start()
            job_id = manager.submit([(source.name, source.stat().st_size, source)],
                                    task="transcribe", language="auto", model="small",
                                    prompt="", delete_inputs=False)[0]["id"]
            self.assertTrue(transcriber.started.wait(2))
            try:
                status = manager.request_model_unload()
                self.assertTrue(status["unload_pending"])
                self.assertTrue(status["busy"])
            finally:
                transcriber.release.set()
            manager.pending.join()
            self.assertEqual(manager.get(job_id)["status"], "done")
            self.assertIsNone(manager.model_status()["loaded_model"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manager = JobManager(Path(self.temp.name), FakeTranscriber())
        self.manager.start()
        self.app = create_app(manager=self.manager)

    def tearDown(self):
        self.temp.cleanup()

    def test_interface_assets(self):
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                home = await client.get("/")
                self.assertEqual(home.status_code, 200)
                self.assertIn("Novo trabalho", home.text)
                self.assertIn('id="history-sidebar" class="history-sidebar"', home.text)
                self.assertLess(home.text.index('class="workspace-grid"'), home.text.index('class="history-sidebar"'))
                self.assertIn('id="sidebar-toggle"', home.text)
                self.assertIn('id="sidebar-close"', home.text)
                self.assertIn('id="sidebar-backdrop"', home.text)
                self.assertIn('<h2 id="history-title">Histórico</h2>', home.text)
                self.assertNotIn("Trabalhos recentes", home.text)
                self.assertNotIn('<header', home.text)
                self.assertNotIn('<footer', home.text)
                sidebar = home.text[home.text.index('<aside id="history-sidebar"'):home.text.index('</aside>')]
                self.assertIn('class="brand"', sidebar)
                self.assertIn('Processamento local', sidebar)
                self.assertIn('id="device-pill"', sidebar)
                self.assertNotIn("Dê voz às suas", home.text)
                self.assertNotIn("SEU ESTÚDIO DE TRANSCRIÇÃO", home.text)
                self.assertIn('id="unload-model-button"', home.text)
                self.assertIn('id="idle-unload-select"', home.text)
                self.assertEqual((await client.get("/static/styles.css")).status_code, 200)
                self.assertEqual((await client.get("/static/app.js")).status_code, 200)
                self.assertEqual((await client.get("/static/secret.txt")).status_code, 404)
        asyncio.run(exercise())

    def test_batch_transcribe_export_and_persist(self):
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                with patch("whisper_ui.app.importlib.util.find_spec", return_value=True):
                    response = await client.post("/api/jobs", files=[
                        ("files", ("um.mp3", b"test-audio", "audio/mpeg")),
                        ("files", ("dois.mp4", b"test-audio", "video/mp4")),
                    ], data={"task": "transcribe", "language": "pt", "model": "small"})
                self.assertEqual(response.status_code, 202)
                jobs = response.json()
                self.assertEqual(len(jobs), 2)
                for _ in range(100):
                    current = (await client.get("/api/jobs")).json()
                    if all(job["status"] == "done" for job in current):
                        break
                    await asyncio.sleep(0.01)
                self.assertTrue(all(job["status"] == "done" for job in current), current)
                detail = (await client.get(f"/api/jobs/{jobs[0]['id']}")).json()
                self.assertEqual(detail["result"]["text"], "Olá, mundo.")
                srt = await client.get(f"/api/jobs/{jobs[0]['id']}/download?format=srt")
                self.assertIn("Olá, mundo.", srt.text)
                archive = zipfile.ZipFile(io.BytesIO((await client.get("/api/export?format=txt")).content))
                self.assertEqual(len(archive.namelist()), 2)
                self.assertEqual(len(JobManager(Path(self.temp.name)).list()), 2)
                self.assertEqual((await client.delete(f"/api/jobs/{jobs[0]['id']}")).status_code, 204)
                self.assertEqual(len((await client.get("/api/jobs")).json()), 1)
                self.assertEqual(list(self.manager.upload_dir.iterdir()), [])
        asyncio.run(exercise())

    def test_rejects_invalid_format(self):
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                with patch("whisper_ui.app.importlib.util.find_spec", return_value=True):
                    response = await client.post("/api/jobs", files={
                        "files": ("notes.txt", b"not audio", "text/plain")
                    })
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(self.manager.upload_dir.iterdir()), [])
        asyncio.run(exercise())

    def test_model_settings_api(self):
        async def exercise():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                self.assertEqual((await client.get("/api/model")).json()["idle_unload_minutes"], 15)
                invalid = await client.put("/api/model/settings", json={"idle_unload_minutes": 2})
                self.assertEqual(invalid.status_code, 400)
                saved = await client.put("/api/model/settings", json={"idle_unload_minutes": 5})
                self.assertEqual(saved.status_code, 200)
                self.assertEqual(saved.json()["idle_unload_minutes"], 5)
                self.assertEqual((await client.post("/api/model/unload")).status_code, 202)
                self.assertEqual((await client.get("/api/model")).json()["idle_unload_minutes"], 5)
        asyncio.run(exercise())

    def test_mcp_transcribes_local_file_and_preserves_input(self):
        async def exercise():
            source = Path(self.temp.name) / "gravacao.mp3"
            source.write_bytes(b"test-audio")
            bad_source = Path(self.temp.name) / "notes.txt"
            bad_source.write_text("not audio", encoding="utf-8")
            async with self.app.router.lifespan_context(self.app):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=self.app),
                    base_url="http://127.0.0.1:7860",
                ) as client:
                    async with streamable_http_client(
                        "http://127.0.0.1:7860/mcp", http_client=client
                    ) as (read, write, _):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            names = {tool.name for tool in (await session.list_tools()).tools}
                            self.assertIn("transcribe_file", names)
                            self.assertIn("translate_file", names)
                            self.assertIn("unload_model", names)
                            self.assertIn("set_model_idle_timeout", names)
                            invalid = await session.call_tool("transcribe_file", {"path": str(bad_source)})
                            self.assertTrue(invalid.isError)
                            with patch("whisper_ui.mcp_server.importlib.util.find_spec", return_value=True):
                                queued = await session.call_tool("transcribe_file", {"path": str(source)})
                            self.assertFalse(queued.isError)
                            job_id = json.loads(queued.content[0].text)["job_id"]
                            status = await session.call_tool("wait_for_job", {
                                "job_id": job_id, "timeout_seconds": 5,
                            })
                            self.assertEqual(json.loads(status.content[0].text)["status"], "done")
                            chunk = await session.call_tool("read_transcript", {
                                "job_id": job_id, "max_chars": 4,
                            })
                            first = json.loads(chunk.content[0].text)
                            self.assertEqual(first["text"], "Olá,")
                            self.assertEqual(first["next_start"], 4)
                            remainder = await session.call_tool("read_transcript", {
                                "job_id": job_id, "start": first["next_start"],
                            })
                            self.assertEqual(first["text"] + json.loads(
                                remainder.content[0].text)["text"], "Olá, mundo.")
                            exported = await session.call_tool("export_transcript", {
                                "job_id": job_id, "format": "srt",
                            })
                            export_path = Path(json.loads(exported.content[0].text)["path"])
                            self.assertIn("Olá, mundo.", export_path.read_text(encoding="utf-8"))
                            jobs = await session.call_tool("list_jobs", {"limit": 1})
                            self.assertEqual(json.loads(jobs.content[0].text)["jobs"][0]["id"], job_id)
                            self.assertEqual((await client.get(f"/api/jobs/{job_id}")).json()["status"], "done")
                            with patch("whisper_ui.mcp_server.importlib.util.find_spec", return_value=True):
                                translated = await session.call_tool("translate_file", {
                                    "path": str(source), "language": "pt", "model": "small",
                                })
                            translation_id = json.loads(translated.content[0].text)["job_id"]
                            self.assertEqual(self.manager.get(translation_id)["task"], "translate")
                            translated_status = await session.call_tool("wait_for_job", {
                                "job_id": translation_id, "timeout_seconds": 5,
                            })
                            self.assertEqual(json.loads(translated_status.content[0].text)["status"], "done")
                            setting = await session.call_tool("set_model_idle_timeout", {"minutes": 5})
                            self.assertEqual(json.loads(setting.content[0].text)["idle_unload_minutes"], 5)
                            unloading = await session.call_tool("unload_model")
                            self.assertFalse(unloading.isError)
                            for _ in range(100):
                                model_status = await session.call_tool("get_model_status")
                                if not json.loads(model_status.content[0].text)["loaded_model"]:
                                    break
                                await asyncio.sleep(0.01)
                            self.assertIsNone(json.loads(model_status.content[0].text)["loaded_model"])
                            self.assertEqual((await client.delete(f"/api/jobs/{job_id}")).status_code, 204)
                            self.assertEqual(source.read_bytes(), b"test-audio")
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
