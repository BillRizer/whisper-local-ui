const $ = (selector) => document.querySelector(selector);
const state = { files: [], jobs: [], selectedId: null, detail: null, view: "text", recorder: null, stream: null, recordStarted: 0, timer: null, previewUrl: null, busy: false, modelStatus: null, modelSettingsBusy: false };
const accepted = new Set(["mp3", "mp4", "m4a", "m4v", "wav", "flac", "ogg", "oga", "opus", "webm", "mov", "mkv", "avi", "aac", "aiff", "wma", "mpeg", "mpga"]);
const mobileSidebar = window.matchMedia("(max-width: 800px)");
let desktopSidebarOpen = true;
try { desktopSidebarOpen = localStorage.getItem("whisper-sidebar-open") !== "false"; } catch (_) { /* storage unavailable */ }
let toastTimeout;

function setSidebar(open, savePreference = false) {
  const sidebar = $("#history-sidebar");
  const toggle = $("#sidebar-toggle");
  $(".workspace-area").inert = open && mobileSidebar.matches;
  if (!open && (sidebar.contains(document.activeElement) || $("#sidebar-backdrop") === document.activeElement)) toggle.focus();
  sidebar.hidden = !open;
  $(".app-layout").classList.toggle("sidebar-hidden", !open);
  toggle.setAttribute("aria-expanded", String(open));
  toggle.setAttribute("aria-label", open ? "Ocultar menu lateral" : "Mostrar menu lateral");
  $("#sidebar-toggle-label").textContent = open ? "Ocultar menu" : "Mostrar menu";
  $("#sidebar-backdrop").hidden = !open || !mobileSidebar.matches;
  document.body.classList.toggle("sidebar-drawer-open", open && mobileSidebar.matches);
  if (savePreference && !mobileSidebar.matches) {
    desktopSidebarOpen = open;
    try { localStorage.setItem("whisper-sidebar-open", String(open)); } catch (_) { /* storage unavailable */ }
  }
}

function toast(message, error = false) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.classList.add("visible");
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => element.classList.remove("visible"), 4200);
}

async function request(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `Erro ${response.status}`;
    try { message = (await response.json()).detail || message; } catch (_) { /* plain response */ }
    throw new Error(message);
  }
  return response.status === 204 ? null : response.json();
}

function fileSize(bytes) {
  return bytes >= 1_000_000 ? `${(bytes / 1_000_000).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

function shortTime(seconds) {
  const value = Math.floor(seconds || 0);
  const h = Math.floor(value / 3600);
  const m = Math.floor(value % 3600 / 60);
  const s = value % 60;
  return h ? `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function setSource(source) {
  const files = source === "files";
  $("#source-files").hidden = !files;
  $("#source-mic").hidden = files;
  for (const [button, active] of [["#tab-files", files], ["#tab-mic", !files]]) {
    $(button).classList.toggle("active", active);
    $(button).setAttribute("aria-selected", String(active));
  }
}

function addFiles(files) {
  for (const file of files) {
    const extension = file.name.split(".").pop().toLowerCase();
    if (!accepted.has(extension)) { toast(`Formato não aceito: ${file.name}`, true); continue; }
    if (file.size > 1_000_000_000) { toast(`Arquivo maior que 1 GB: ${file.name}`, true); continue; }
    if (state.files.length >= 20) { toast("Máximo de 20 arquivos por vez.", true); break; }
    state.files.push(file);
  }
  renderSelectedFiles();
}

function renderSelectedFiles() {
  const list = $("#file-list");
  list.replaceChildren();
  list.hidden = state.files.length === 0;
  state.files.forEach((file, index) => {
    const row = document.createElement("div"); row.className = "selected-file";
    const icon = document.createElement("span");
    icon.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4.5h10l5 5v10A1.5 1.5 0 0 1 17.5 21h-12A1.5 1.5 0 0 1 4 19.5z"/><path d="M14 4.5v5h5"/></svg>';
    const name = document.createElement("span"); name.className = "selected-file-name"; name.textContent = file.name;
    const size = document.createElement("span"); size.className = "selected-file-size"; size.textContent = fileSize(file.size);
    const remove = document.createElement("button"); remove.className = "remove-file"; remove.type = "button"; remove.title = `Remover ${file.name}`; remove.setAttribute("aria-label", remove.title); remove.textContent = "×";
    remove.onclick = () => { state.files.splice(index, 1); renderSelectedFiles(); };
    row.append(icon, name, size, remove); list.append(row);
  });
  updateSubmit();
}

function updateSubmit() {
  const task = document.querySelector('input[name="task"]:checked').value;
  $("#submit-button span").textContent = task === "translate" ? "Traduzir para inglês" : state.files.length > 1 ? `Transcrever ${state.files.length} arquivos` : "Transcrever arquivo";
  $("#submit-button").disabled = state.files.length === 0 || state.busy;
  for (const [id, selected] of [["#option-transcribe", task === "transcribe"], ["#option-translate", task === "translate"]]) $(id).classList.toggle("selected", selected);
  $("#model-note").textContent = $("#model-select").value === "large-v3"
    ? "Large v3: cerca de 2,9 GB no primeiro download. O andamento aparece no resultado."
    : "O modelo é baixado uma vez; depois o processamento funciona localmente.";
}

async function submit() {
  if (!state.files.length || state.busy) return;
  state.busy = true; updateSubmit();
  const button = $("#submit-button span"); const original = button.textContent; button.textContent = "Enviando arquivos…";
  const data = new FormData();
  state.files.forEach(file => data.append("files", file));
  data.append("task", document.querySelector('input[name="task"]:checked').value);
  data.append("language", $("#language-select").value);
  data.append("model", $("#model-select").value);
  data.append("prompt", $("#prompt-input").value.trim());
  try {
    const jobs = await request("/api/jobs", { method: "POST", body: data });
    state.files = []; renderSelectedFiles();
    state.selectedId = jobs[0].id; state.detail = null;
    toast(jobs.length === 1 ? "Arquivo adicionado à fila." : `${jobs.length} arquivos adicionados à fila.`);
    await refreshJobs();
    $("#history-list").scrollTop = 0;
    if (window.matchMedia("(max-width: 800px)").matches) $("#result-title").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) { toast(error.message, true); }
  finally { state.busy = false; button.textContent = original; updateSubmit(); }
}

function chooseMime() {
  for (const type of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]) {
    if (MediaRecorder.isTypeSupported(type)) return type;
  }
  return "";
}

async function toggleRecording() {
  if (state.recorder?.state === "recording") { state.recorder.stop(); return; }
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) { toast("Este navegador não oferece gravação de microfone.", true); return; }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = chooseMime();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks = [];
    recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
    recorder.onerror = () => toast("A gravação falhou. Tente novamente.", true);
    recorder.onstop = () => {
      clearInterval(state.timer); state.timer = null;
      stream.getTracks().forEach(track => track.stop()); state.stream = null;
      $("#mic-box").classList.remove("recording");
      $("#record-button").innerHTML = "<span></span> Gravar novamente";
      const type = recorder.mimeType || mimeType || "audio/webm";
      const extension = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
      const blob = new Blob(chunks, { type });
      if (blob.size) {
        addFiles([new File([blob], `gravacao-${new Date().toISOString().replace(/[:.]/g, "-")}.${extension}`, { type })]);
        if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
        state.previewUrl = URL.createObjectURL(blob);
        $("#record-preview").src = state.previewUrl; $("#record-preview").hidden = false;
        $("#mic-title").textContent = "Gravação pronta";
        $("#mic-description").textContent = "Ela foi adicionada aos arquivos para processar.";
      }
    };
    state.stream = stream; state.recorder = recorder; state.recordStarted = Date.now();
    recorder.start(1000);
    $("#mic-box").classList.add("recording");
    $("#record-button").innerHTML = "<span></span> Parar gravação";
    $("#mic-title").textContent = "Gravando seu áudio…";
    $("#mic-description").textContent = "Fale normalmente. Pare quando terminar.";
    $("#record-preview").hidden = true;
    const updateTimer = () => { $("#record-timer").textContent = shortTime((Date.now() - state.recordStarted) / 1000); };
    updateTimer(); state.timer = setInterval(updateTimer, 1000);
  } catch (error) { stream?.getTracks().forEach(track => track.stop()); toast(error.name === "NotAllowedError" ? "Permita o uso do microfone no navegador." : `Microfone indisponível: ${error.message}`, true); }
}

const labels = { queued: "Na fila", running: "Processando", done: "Concluído", error: "Falhou" };

function renderHistory() {
  const list = $("#history-list");
  const scrollTop = list.scrollTop;
  const focused = list.contains(document.activeElement) ? {
    jobId: document.activeElement.dataset.jobId,
    action: document.activeElement.dataset.action,
  } : null;
  list.replaceChildren();
  $("#job-count").textContent = state.jobs.length;
  const hasDone = state.jobs.some(job => job.status === "done");
  $("#batch-download").classList.toggle("disabled", !hasDone);
  $("#batch-download").setAttribute("aria-disabled", String(!hasDone));
  if (!state.jobs.length) {
    const empty = document.createElement("div"); empty.className = "history-empty";
    empty.textContent = "Nenhum trabalho ainda. Seus resultados salvos aparecem aqui.";
    list.append(empty); return;
  }
  for (const job of state.jobs) {
    const row = document.createElement("div"); row.className = `job-row${job.id === state.selectedId ? " active" : ""}`;
    const open = document.createElement("button"); open.type = "button"; open.className = "job-select";
    open.dataset.jobId = job.id; open.dataset.action = "open";
    open.setAttribute("aria-label", `Ver ${job.name}`);
    if (job.id === state.selectedId) open.setAttribute("aria-current", "true");
    const name = document.createElement("div"); name.className = "job-name"; name.textContent = job.name;
    const sub = document.createElement("div"); sub.className = "job-sub";
    sub.textContent = `${job.task === "translate" ? "Tradução" : "Transcrição"} · ${new Date(job.created_at).toLocaleString("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}`;
    const status = document.createElement("div"); status.className = `job-state ${job.status}`;
    status.textContent = job.status === "running" ? `${labels[job.status]} ${Math.round(job.progress * 100)}%` : labels[job.status] || job.status;
    open.append(name, sub, status);
    open.onclick = () => selectJob(job.id);
    const remove = document.createElement("button"); remove.type = "button"; remove.className = "job-delete";
    remove.dataset.jobId = job.id; remove.dataset.action = "remove";
    remove.title = `Excluir ${job.name}`; remove.setAttribute("aria-label", remove.title); remove.textContent = "×";
    remove.onclick = async () => {
      if (job.status === "running") { toast("Aguarde o processamento terminar.", true); return; }
      if (!window.confirm(`Excluir ${job.name} do histórico?`)) return;
      try {
        await request(`/api/jobs/${job.id}`, { method: "DELETE" });
        if (state.selectedId === job.id) { state.selectedId = null; state.detail = null; }
        await refreshJobs(); toast("Trabalho removido.");
      } catch (error) { toast(error.message, true); }
    };
    row.append(open, remove); list.append(row);
  }
  list.scrollTop = scrollTop;
  if (focused?.jobId) {
    const target = [...list.querySelectorAll("button")].find(button => button.dataset.jobId === focused.jobId && button.dataset.action === focused.action);
    (target || list.querySelector(".job-select"))?.focus({ preventScroll: true });
  }
}

async function selectJob(id) {
  if (mobileSidebar.matches) setSidebar(false);
  state.selectedId = id; state.detail = null; renderHistory(); await refreshDetail();
  if (window.matchMedia("(max-width: 800px)").matches) $("#result-title").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function refreshJobs() {
  try {
    state.jobs = await request("/api/jobs");
    if (state.selectedId && !state.jobs.some(job => job.id === state.selectedId)) { state.selectedId = null; state.detail = null; }
    if (!state.selectedId && state.jobs.length) state.selectedId = state.jobs[0].id;
    renderHistory(); await refreshDetail();
  } catch (error) { toast(error.message, true); }
}

async function refreshDetail() {
  const summary = state.jobs.find(job => job.id === state.selectedId);
  $("#result-empty").hidden = !!summary;
  $("#result-content").hidden = !summary;
  $("#copy-button").hidden = !summary || summary.status !== "done";
  if (!summary) return;
  $("#result-name").textContent = summary.name;
  $("#result-status").textContent = labels[summary.status] || summary.status;
  $("#result-status").className = `status-badge ${summary.status}`;
  $("#result-details").textContent = summary.status === "done" ? `${shortTime(summary.duration)} · ${summary.device === "cuda" ? "GPU" : "CPU"}` : summary.model;
  $("#result-progress").hidden = !["queued", "running"].includes(summary.status);
  $("#result-error").hidden = summary.status !== "error";
  $("#result-ready").hidden = summary.status !== "done";
  if (["queued", "running"].includes(summary.status)) {
    $("#result-progress-bar").style.width = `${Math.round(summary.progress * 100)}%`;
    const elapsed = summary.status === "running" ? ` · ${shortTime((Date.now() - new Date(summary.created_at).getTime()) / 1000)} decorridos` : "";
    $("#result-progress-message").textContent = (summary.message || "Aguarde…") + elapsed;
  }
  if (summary.status === "error") $("#result-error").textContent = summary.error || "Não foi possível processar este arquivo.";
  if (summary.status === "done" && (!state.detail || state.detail.id !== summary.id)) {
    try { const detail = await request(`/api/jobs/${summary.id}`); if (state.selectedId !== summary.id) return; state.detail = detail; renderTranscript(); }
    catch (error) { toast(error.message, true); }
  }
}

function renderTranscript() {
  if (!state.detail?.result) return;
  const result = state.detail.result;
  $("#transcript-text").textContent = result.text;
  const segments = $("#transcript-segments"); segments.replaceChildren();
  for (const segment of result.segments) {
    const row = document.createElement("div"); row.className = "segment";
    const time = document.createElement("span"); time.className = "segment-time"; time.textContent = shortTime(segment.start);
    const text = document.createElement("span"); text.textContent = segment.text;
    row.append(time, text); segments.append(row);
  }
  setView(state.view);
}

function setView(view) {
  state.view = view;
  $("#transcript-text").hidden = view !== "text";
  $("#transcript-segments").hidden = view !== "segments";
  for (const [id, active] of [["#view-text", view === "text"], ["#view-segments", view === "segments"]]) { $(id).classList.toggle("active", active); $(id).setAttribute("aria-selected", String(active)); }
}

async function loadSystem() {
  try {
    const system = await request("/api/system");
    const label = $("#device-label"); const pill = $("#device-pill");
    if (!system.engine_installed) { label.textContent = "Instale o modelo"; pill.classList.add("cpu"); }
    else if (system.device === "cuda") label.textContent = "GPU pronta";
    else { label.textContent = "CPU ativa"; pill.classList.add("cpu"); }
  } catch (_) { $("#device-label").textContent = "Dispositivo indisponível"; }
}

function renderModelStatus(status) {
  state.modelStatus = status;
  const label = $("#model-memory-status");
  if (status.error) label.textContent = `Falha ao descarregar: ${status.error}`;
  else if (status.unload_pending) label.textContent = "Descarregamento agendado após a fila";
  else if (status.busy) label.textContent = `Em uso: ${status.active_model}`;
  else if (status.loaded_model) label.textContent = `Carregado: ${status.loaded_model} · ${status.device === "cuda" ? "GPU" : "CPU"}`;
  else label.textContent = "Nenhum modelo carregado";
  $("#unload-model-button").disabled = status.unload_pending || (!status.loaded_model && !status.busy);
  const select = $("#idle-unload-select");
  if (!state.modelSettingsBusy && document.activeElement !== select) select.value = String(status.idle_unload_minutes);
  select.disabled = state.modelSettingsBusy;
}

async function refreshModelStatus() {
  try { renderModelStatus(await request("/api/model")); }
  catch (_) { $("#model-memory-status").textContent = "Estado do modelo indisponível"; }
}

async function changeIdleUnload() {
  const select = $("#idle-unload-select");
  const previous = state.modelStatus?.idle_unload_minutes;
  state.modelSettingsBusy = true; select.disabled = true;
  try {
    const status = await request("/api/model/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ idle_unload_minutes: Number(select.value) }) });
    renderModelStatus(status);
    toast(status.idle_unload_minutes ? `Modelo será descarregado após ${status.idle_unload_minutes} minuto(s) de inatividade.` : "Descarregamento automático desativado.");
  } catch (error) {
    if (previous !== undefined) select.value = String(previous);
    toast(error.message, true);
  } finally { state.modelSettingsBusy = false; select.disabled = false; }
}

async function unloadCurrentModel() {
  const button = $("#unload-model-button"); button.disabled = true;
  try {
    const status = await request("/api/model/unload", { method: "POST" });
    renderModelStatus(status);
    toast(status.unload_pending ? "Modelo será descarregado após os trabalhos na fila." : "Modelo descarregado da memória.");
  } catch (error) { toast(error.message, true); await refreshModelStatus(); }
}

$("#tab-files").onclick = () => setSource("files");
$("#tab-mic").onclick = () => setSource("mic");
$("#file-input").onchange = event => { addFiles(event.target.files); event.target.value = ""; };
$("#dropzone").onclick = () => $("#file-input").click();
$("#dropzone").onkeydown = event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("#file-input").click(); } };
$("#dropzone").ondragover = event => { event.preventDefault(); $("#dropzone").classList.add("dragging"); };
$("#dropzone").ondragleave = () => $("#dropzone").classList.remove("dragging");
$("#dropzone").ondrop = event => { event.preventDefault(); $("#dropzone").classList.remove("dragging"); addFiles(event.dataTransfer.files); };
document.querySelectorAll('input[name="task"]').forEach(input => input.onchange = updateSubmit);
$("#model-select").onchange = updateSubmit;
$("#idle-unload-select").onchange = changeIdleUnload;
$("#unload-model-button").onclick = unloadCurrentModel;
$("#record-button").onclick = toggleRecording;
$("#submit-button").onclick = submit;
$("#view-text").onclick = () => setView("text");
$("#view-segments").onclick = () => setView("segments");
$("#copy-button").onclick = async () => { try { await navigator.clipboard.writeText(state.detail.result.text); toast("Texto copiado."); } catch (_) { toast("Não foi possível copiar o texto.", true); } };
document.querySelectorAll("[data-download]").forEach(button => button.onclick = () => { if (state.selectedId) window.location.href = `/api/jobs/${state.selectedId}/download?format=${button.dataset.download}`; });
$("#batch-format").onchange = () => $("#batch-download").href = `/api/export?format=${$("#batch-format").value}`;
$("#batch-format").dispatchEvent(new Event("change"));
$("#batch-download").onclick = event => { if (!state.jobs.some(job => job.status === "done")) event.preventDefault(); };
$("#sidebar-toggle").onclick = () => {
  const open = $("#history-sidebar").hidden;
  setSidebar(open, true);
  if (open && mobileSidebar.matches) $("#sidebar-close").focus();
};
$("#sidebar-close").onclick = () => setSidebar(false);
$("#sidebar-backdrop").onclick = () => setSidebar(false);
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && mobileSidebar.matches && !$("#history-sidebar").hidden) setSidebar(false);
});
mobileSidebar.addEventListener("change", () => setSidebar(mobileSidebar.matches ? false : desktopSidebarOpen));
setSidebar(mobileSidebar.matches ? false : desktopSidebarOpen);
loadSystem(); refreshJobs(); refreshModelStatus();
setInterval(() => { refreshJobs(); refreshModelStatus(); }, 2200);
