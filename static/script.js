const audio = document.getElementById("radioAudio");
const mainPlayButton = document.getElementById("mainPlayButton");
const dockPlayButton = document.getElementById("dockPlayButton");
const mainPlayIcon = document.getElementById("mainPlayIcon");
const dockPlayIcon = document.getElementById("dockPlayIcon");
const mainPlayText = document.getElementById("mainPlayText");
const identifyButton = document.getElementById("identifyButton");
const volumeControl = document.getElementById("volumeControl");
const muteButton = document.getElementById("muteButton");
const currentCover = document.getElementById("currentCover");
const currentTitle = document.getElementById("currentTitle");
const currentArtist = document.getElementById("currentArtist");
const dockCover = document.getElementById("dockCover");
const dockTitle = document.getElementById("dockTitle");
const dockArtist = document.getElementById("dockArtist");
const historyList = document.getElementById("historyList");
const topList = document.getElementById("topList");
const radioStatus = document.getElementById("radioStatus");
const statusLight = document.getElementById("statusLight");
const identifyState = document.getElementById("identifyState");
const vinylDisc = document.getElementById("vinylDisc");
const canvas = document.getElementById("spectrum");
const ctx = canvas.getContext("2d");

const STORAGE_KEY = "m80_ballads_vercel_data_v1";
const STREAM_URL = audio.querySelector("source")?.src || "https://stream-icy.bauermedia.pt/m80ballads.aac";
let isPlaying = false;
let identifyTimer = null;
let animationFrame = null;
let fakePhase = 0;
let lastVolume = 0.8;
let store = loadStore();

audio.volume = 0.8;

function loadStore() {
    try {
        const value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
        return {
            current: value.current || null,
            history: Array.isArray(value.history) ? value.history : [],
            top: value.top && typeof value.top === "object" ? value.top : {}
        };
    } catch {
        return { current: null, history: [], top: {} };
    }
}

function saveStore() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}

function safeText(value, fallback = "") {
    return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function formatTime(timestamp) {
    if (!timestamp) return "";
    return new Date(timestamp * 1000).toLocaleTimeString("pt-PT", {
        hour: "2-digit",
        minute: "2-digit"
    });
}

function setPlayingUI(playing) {
    isPlaying = playing;
    document.body.classList.toggle("playing", playing);
    vinylDisc.classList.toggle("playing", playing);
    statusLight.classList.toggle("active", playing);
    mainPlayIcon.textContent = playing ? "❚❚" : "▶";
    dockPlayIcon.textContent = playing ? "❚❚" : "▶";
    mainPlayText.textContent = playing ? "Desligar rádio" : "Ligar rádio";
    dockPlayButton.setAttribute("aria-label", playing ? "Pausar" : "Reproduzir");
    radioStatus.textContent = playing ? "M80 Ballads ligada" : "Rádio desligada";
}

function waitForPlaying(timeoutMs = 15000) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(() => finish(new Error("O stream demorou demasiado a responder.")), timeoutMs);
        const onPlaying = () => finish();
        const onError = () => finish(new Error("O navegador não conseguiu abrir o stream AAC."));
        function finish(error) {
            clearTimeout(timer);
            audio.removeEventListener("playing", onPlaying);
            audio.removeEventListener("error", onError);
            error ? reject(error) : resolve();
        }
        audio.addEventListener("playing", onPlaying, { once: true });
        audio.addEventListener("error", onError, { once: true });
    });
}

async function toggleRadio() {
    if (isPlaying) {
        audio.pause();
        audio.removeAttribute("src");
        audio.load();
        clearInterval(identifyTimer);
        setPlayingUI(false);
        return;
    }

    mainPlayButton.disabled = true;
    dockPlayButton.disabled = true;
    radioStatus.textContent = "A ligar diretamente à M80 Ballads…";

    try {
        audio.src = `${STREAM_URL}${STREAM_URL.includes("?") ? "&" : "?"}nocache=${Date.now()}`;
        audio.load();
        const ready = waitForPlaying();
        await audio.play();
        await ready;
        setPlayingUI(true);

        setTimeout(() => {
            if (isPlaying) identifyTrack(false);
        }, 8000);

        clearInterval(identifyTimer);
        identifyTimer = setInterval(() => {
            if (isPlaying) identifyTrack(true);
        }, 60000);
    } catch (error) {
        console.error(error);
        setPlayingUI(false);
        radioStatus.textContent = `Não foi possível iniciar a rádio: ${error.message}`;
    } finally {
        mainPlayButton.disabled = false;
        dockPlayButton.disabled = false;
    }
}

function sameTrack(a, b) {
    if (!a || !b) return false;
    return `${a.artist}—${a.title}`.toLocaleLowerCase() === `${b.artist}—${b.title}`.toLocaleLowerCase();
}

function rememberTrack(track) {
    const previous = store.current;
    store.current = track;

    if (!sameTrack(previous, track)) {
        store.history.unshift({ ...track, played_at: Math.floor(Date.now() / 1000) });
        store.history = store.history.slice(0, 10);
        const key = `${track.artist}—${track.title}`.toLocaleLowerCase();
        const old = store.top[key] || { ...track, count: 0 };
        store.top[key] = { ...old, ...track, count: Number(old.count || 0) + 1 };
    }

    saveStore();
    renderAll();
}

async function identifyTrack(silent = false) {
    if (identifyButton.disabled) return;
    identifyButton.disabled = true;
    identifyState.textContent = "A Vercel está a gravar uma pequena amostra para o Shazam…";
    if (!silent) identifyButton.innerHTML = "<span>◌</span> A identificar…";

    try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 58000);
        const response = await fetch("/api/identify", {
            method: "POST",
            cache: "no-store",
            signal: controller.signal
        });
        clearTimeout(timeout);
        const data = await response.json();

        if (data.track) {
            rememberTrack(data.track);
            identifyState.textContent = "Música identificada pelo Shazam";
        } else {
            identifyState.textContent = data.error || "O Shazam não reconheceu esta parte da emissão.";
        }
    } catch (error) {
        identifyState.textContent = error.name === "AbortError"
            ? "A identificação excedeu o tempo permitido. Tenta novamente."
            : "Erro ao contactar a identificação da Vercel.";
        console.error(error);
    } finally {
        identifyButton.disabled = false;
        identifyButton.innerHTML = "<span>✦</span> Identificar agora";
    }
}

function updateCurrent(track) {
    if (!track) return;
    const title = safeText(track.title, "M80 Ballads");
    const artist = safeText(track.artist, "Rádio Neon Gold");
    const cover = safeText(track.cover, "/static/default_cover.svg");
    currentTitle.textContent = title;
    currentArtist.textContent = artist;
    dockTitle.textContent = title;
    dockArtist.textContent = artist;
    currentCover.src = cover;
    dockCover.src = cover;
    currentCover.onerror = () => { currentCover.src = "/static/default_cover.svg"; };
    dockCover.onerror = () => { dockCover.src = "/static/default_cover.svg"; };
    document.title = `${title} — ${artist} | M80 Ballads`;
}

function renderHistory(items) {
    if (!items.length) {
        historyList.className = "track-list empty-state";
        historyList.textContent = "Ainda não existem músicas identificadas neste navegador.";
        return;
    }
    historyList.className = "track-list";
    historyList.innerHTML = items.slice(0, 10).map((item, index) => `
        <div class="track-item">
            <span class="track-rank">${String(index + 1).padStart(2, "0")}</span>
            <img src="${item.cover || "/static/default_cover.svg"}" alt="" onerror="this.src='/static/default_cover.svg'">
            <div class="track-text">
                <strong>${escapeHtml(item.title || "Música desconhecida")}</strong>
                <span>${escapeHtml(item.artist || "Artista desconhecido")}</span>
            </div>
            <span class="track-time">${formatTime(item.played_at)}</span>
        </div>`).join("");
}

function renderTop() {
    const items = Object.values(store.top).sort((a, b) => Number(b.count || 0) - Number(a.count || 0)).slice(0, 10);
    if (!items.length) {
        topList.className = "track-list empty-state";
        topList.textContent = "O Top 10 será criado neste navegador à medida que ouvires a rádio.";
        return;
    }
    topList.className = "track-list";
    topList.innerHTML = items.map((item, index) => `
        <div class="track-item">
            <span class="track-rank">${String(index + 1).padStart(2, "0")}</span>
            <img src="${item.cover || "/static/default_cover.svg"}" alt="" onerror="this.src='/static/default_cover.svg'">
            <div class="track-text">
                <strong>${escapeHtml(item.title || "Música desconhecida")}</strong>
                <span>${escapeHtml(item.artist || "Artista desconhecido")}</span>
            </div>
            <span class="track-count">${item.count || 1}×</span>
        </div>`).join("");
}

function renderAll() {
    if (store.current) updateCurrent(store.current);
    renderHistory(store.history);
    renderTop();
}

function resizeCanvas() {
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rect.width * ratio));
    canvas.height = Math.max(1, Math.floor(rect.height * ratio));
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function drawSpectrum() {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    ctx.clearRect(0, 0, width, height);
    const bars = Math.max(32, Math.floor(width / 13));
    const gap = 4;
    const barWidth = Math.max(2, (width - gap * (bars - 1)) / bars);
    fakePhase += isPlaying ? 0.055 : 0.018;

    for (let i = 0; i < bars; i++) {
        const wave = Math.sin(fakePhase + i * 0.33) * 0.22 + Math.sin(fakePhase * 0.63 + i * 0.14) * 0.18;
        const power = Math.min(1, Math.max(0.035, isPlaying ? 0.32 + wave + Math.random() * 0.23 : 0.08 + wave * 0.12));
        const barHeight = Math.max(3, power * height * 0.78);
        const x = i * (barWidth + gap);
        const y = height - barHeight;
        const gradient = ctx.createLinearGradient(0, y, 0, height);
        gradient.addColorStop(0, "rgba(255, 230, 155, 0.95)");
        gradient.addColorStop(0.45, "rgba(238, 176, 67, 0.75)");
        gradient.addColorStop(1, "rgba(126, 75, 17, 0.12)");
        ctx.fillStyle = gradient;
        ctx.shadowColor = "rgba(241, 185, 76, 0.25)";
        ctx.shadowBlur = 9;
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barHeight, Math.min(5, barWidth / 2));
        ctx.fill();
    }
    ctx.shadowBlur = 0;
    animationFrame = requestAnimationFrame(drawSpectrum);
}

mainPlayButton.addEventListener("click", toggleRadio);
dockPlayButton.addEventListener("click", toggleRadio);
identifyButton.addEventListener("click", () => identifyTrack(false));

volumeControl.addEventListener("input", (event) => {
    const value = Number(event.target.value) / 100;
    audio.volume = value;
    audio.muted = value === 0;
    muteButton.textContent = value === 0 ? "🔇" : value < 0.5 ? "🔉" : "🔊";
    if (value > 0) lastVolume = value;
});

muteButton.addEventListener("click", () => {
    if (audio.muted || audio.volume === 0) {
        audio.muted = false;
        audio.volume = lastVolume || 0.8;
        volumeControl.value = String(Math.round(audio.volume * 100));
        muteButton.textContent = audio.volume < 0.5 ? "🔉" : "🔊";
    } else {
        lastVolume = audio.volume;
        audio.muted = true;
        muteButton.textContent = "🔇";
    }
});

audio.addEventListener("playing", () => setPlayingUI(true));
audio.addEventListener("pause", () => setPlayingUI(false));
audio.addEventListener("error", () => {
    setPlayingUI(false);
    radioStatus.textContent = "Ligação ao stream interrompida";
});
window.addEventListener("resize", resizeCanvas);
window.addEventListener("beforeunload", () => {
    clearInterval(identifyTimer);
    cancelAnimationFrame(animationFrame);
});

resizeCanvas();
drawSpectrum();
renderAll();
