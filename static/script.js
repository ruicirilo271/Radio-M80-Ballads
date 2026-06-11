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
const spectrumState = document.getElementById("spectrumState");
const vinylDisc = document.getElementById("vinylDisc");
const canvas = document.getElementById("spectrum");
const ctx = canvas.getContext("2d");

const STORAGE_KEY = "m80_ballads_neon_gold_v3";
const STREAM_URL = "/radio-stream";
const DEFAULT_COVER = "/static/default_cover.svg";

let isPlaying = false;
let identifyTimer = null;
let animationFrame = null;
let lastVolume = 0.8;
let audioContext = null;
let analyser = null;
let sourceNode = null;
let frequencyData = null;
let smoothedData = null;
let store = loadStore();

audio.volume = 0.8;

function loadStore() {
    try {
        const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
        return {
            current: saved?.current || null,
            history: Array.isArray(saved?.history) ? saved.history.slice(0, 10) : [],
            top: saved?.top && typeof saved.top === "object" ? saved.top : {},
        };
    } catch {
        return { current: null, history: [], top: {} };
    }
}

function saveStore() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}

function escapeHtml(value) {
    return String(value ?? "")
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
        minute: "2-digit",
    });
}

function trackKey(track) {
    return `${track.artist || ""} — ${track.title || ""}`.trim().toLocaleLowerCase("pt-PT");
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
    if (!playing) spectrumState.textContent = "Spectrum: rádio parada";
}

async function initializeAudioGraph() {
    if (!audioContext) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (!AudioContextClass) {
            throw new Error("Este navegador não suporta Web Audio API.");
        }

        audioContext = new AudioContextClass();
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 512;
        analyser.minDecibels = -95;
        analyser.maxDecibels = -15;
        analyser.smoothingTimeConstant = 0.78;

        sourceNode = audioContext.createMediaElementSource(audio);
        sourceNode.connect(analyser);
        analyser.connect(audioContext.destination);

        frequencyData = new Uint8Array(analyser.frequencyBinCount);
        smoothedData = new Float32Array(analyser.frequencyBinCount);
    }

    if (audioContext.state === "suspended") {
        await audioContext.resume();
    }
}

async function startRadio() {
    mainPlayButton.disabled = true;
    dockPlayButton.disabled = true;
    radioStatus.textContent = "A ligar ao stream da M80…";

    try {
        await initializeAudioGraph();

        audio.pause();
        audio.src = `${STREAM_URL}?t=${Date.now()}`;
        audio.load();
        await audio.play();

        setPlayingUI(true);
        spectrumState.textContent = "Spectrum real: frequências ativas";

        clearInterval(identifyTimer);
        setTimeout(() => identifyTrack(true), 8000);
        identifyTimer = setInterval(() => {
            if (isPlaying) identifyTrack(true);
        }, 60000);
    } catch (error) {
        console.error("Erro ao iniciar rádio:", error);
        setPlayingUI(false);
        radioStatus.textContent = `Não foi possível iniciar: ${error.message || error}`;
        spectrumState.textContent = "Spectrum: sem acesso ao áudio";
    } finally {
        mainPlayButton.disabled = false;
        dockPlayButton.disabled = false;
    }
}

function stopRadio() {
    clearInterval(identifyTimer);
    identifyTimer = null;
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    setPlayingUI(false);
}

async function toggleRadio() {
    if (isPlaying) stopRadio();
    else await startRadio();
}

async function identifyTrack(silent = false) {
    if (identifyButton.disabled) return;

    identifyButton.disabled = true;
    identifyState.textContent = "A gravar uma amostra e identificar…";
    if (!silent) identifyButton.innerHTML = "<span>◌</span> A identificar…";

    try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 48000);
        const response = await fetch("/api/identify", {
            method: "POST",
            signal: controller.signal,
        });
        clearTimeout(timeout);

        const data = await response.json();
        if (!response.ok || !data.track) {
            throw new Error(data.error || "A música não foi reconhecida.");
        }

        addIdentifiedTrack(data.track);
        identifyState.textContent = "Música identificada pelo Shazam";
    } catch (error) {
        if (!silent) identifyState.textContent = error.name === "AbortError"
            ? "A identificação excedeu o tempo disponível."
            : (error.message || "Erro ao identificar a música.");
        console.warn("Identificação:", error);
    } finally {
        identifyButton.disabled = false;
        identifyButton.innerHTML = "<span>✦</span> Identificar agora";
    }
}

function addIdentifiedTrack(track) {
    const normalized = {
        title: String(track.title || "Música desconhecida").trim(),
        artist: String(track.artist || "Artista desconhecido").trim(),
        cover: track.cover || DEFAULT_COVER,
        played_at: track.played_at || Math.floor(Date.now() / 1000),
        identified_at: track.identified_at || Math.floor(Date.now() / 1000),
    };

    const key = trackKey(normalized);
    const previousKey = store.current ? trackKey(store.current) : "";
    store.current = normalized;

    if (key !== previousKey) {
        store.history = [normalized, ...store.history.filter(item => trackKey(item) !== key)].slice(0, 10);
        const previous = store.top[key] || { ...normalized, count: 0 };
        store.top[key] = { ...normalized, count: Number(previous.count || 0) + 1 };
    }

    saveStore();
    renderAll();
}

function updateCurrent(track) {
    if (!track) return;
    const title = track.title || "M80 Ballads";
    const artist = track.artist || "Rádio Neon Gold";
    const cover = track.cover || DEFAULT_COVER;

    currentTitle.textContent = title;
    currentArtist.textContent = artist;
    dockTitle.textContent = title;
    dockArtist.textContent = artist;
    currentCover.src = cover;
    dockCover.src = cover;
    currentCover.onerror = () => { currentCover.src = DEFAULT_COVER; };
    dockCover.onerror = () => { dockCover.src = DEFAULT_COVER; };
    document.title = `${title} — ${artist} | M80 Ballads`;
}

function renderHistory() {
    if (!store.history.length) {
        historyList.className = "track-list empty-state";
        historyList.textContent = "Ainda não existem músicas identificadas.";
        return;
    }

    historyList.className = "track-list";
    historyList.innerHTML = store.history.slice(0, 10).map((item, index) => `
        <div class="track-item">
            <span class="track-rank">${String(index + 1).padStart(2, "0")}</span>
            <img src="${escapeHtml(item.cover || DEFAULT_COVER)}" alt="" onerror="this.src='${DEFAULT_COVER}'">
            <div class="track-text">
                <strong>${escapeHtml(item.title)}</strong>
                <span>${escapeHtml(item.artist)}</span>
            </div>
            <span class="track-time">${formatTime(item.played_at)}</span>
        </div>`).join("");
}

function renderTop() {
    const items = Object.values(store.top)
        .sort((a, b) => Number(b.count || 0) - Number(a.count || 0))
        .slice(0, 10);

    if (!items.length) {
        topList.className = "track-list empty-state";
        topList.textContent = "O Top 10 será criado neste navegador à medida que ouvires a rádio.";
        return;
    }

    topList.className = "track-list";
    topList.innerHTML = items.map((item, index) => `
        <div class="track-item">
            <span class="track-rank">${String(index + 1).padStart(2, "0")}</span>
            <img src="${escapeHtml(item.cover || DEFAULT_COVER)}" alt="" onerror="this.src='${DEFAULT_COVER}'">
            <div class="track-text">
                <strong>${escapeHtml(item.title)}</strong>
                <span>${escapeHtml(item.artist)}</span>
            </div>
            <span class="track-count">${Number(item.count || 1)}×</span>
        </div>`).join("");
}

function renderAll() {
    if (store.current) updateCurrent(store.current);
    renderHistory();
    renderTop();
}

function resizeCanvas() {
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.floor(rect.width * ratio));
    canvas.height = Math.max(1, Math.floor(rect.height * ratio));
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}

function roundedBar(x, y, width, height, radius) {
    const r = Math.min(radius, width / 2, height / 2);
    ctx.beginPath();
    if (typeof ctx.roundRect === "function") {
        ctx.roundRect(x, y, width, height, r);
    } else {
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + width - r, y);
        ctx.quadraticCurveTo(x + width, y, x + width, y + r);
        ctx.lineTo(x + width, y + height - r);
        ctx.quadraticCurveTo(x + width, y + height, x + width - r, y + height);
        ctx.lineTo(x + r, y + height);
        ctx.quadraticCurveTo(x, y + height, x, y + height - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
    }
    ctx.fill();
}

function drawSpectrum() {
    const width = Math.max(1, canvas.clientWidth);
    const height = Math.max(1, canvas.clientHeight);
    ctx.clearRect(0, 0, width, height);

    const bars = Math.max(36, Math.floor(width / 12));
    const gap = width < 500 ? 3 : 4;
    const barWidth = Math.max(2, (width - gap * (bars - 1)) / bars);

    if (analyser && frequencyData && smoothedData && isPlaying) {
        analyser.getByteFrequencyData(frequencyData);
    }

    for (let i = 0; i < bars; i++) {
        let power = 0.035;

        if (analyser && frequencyData && smoothedData && isPlaying) {
            const usableBins = Math.floor(frequencyData.length * 0.72);
            const curvedPosition = Math.pow(i / Math.max(1, bars - 1), 1.65);
            const bin = Math.min(usableBins - 1, Math.floor(curvedPosition * usableBins));
            const raw = frequencyData[bin] / 255;
            smoothedData[bin] += (raw - smoothedData[bin]) * 0.35;
            const envelope = 0.72 + Math.sin((i / bars) * Math.PI) * 0.28;
            power = Math.max(0.025, Math.min(1, Math.pow(smoothedData[bin], 0.72) * envelope));
        }

        const barHeight = Math.max(3, power * height * 0.9);
        const x = i * (barWidth + gap);
        const y = height - barHeight;
        const gradient = ctx.createLinearGradient(0, y, 0, height);
        gradient.addColorStop(0, "rgba(255, 238, 181, 0.98)");
        gradient.addColorStop(0.35, "rgba(244, 190, 81, 0.9)");
        gradient.addColorStop(1, "rgba(117, 68, 12, 0.16)");

        ctx.fillStyle = gradient;
        ctx.shadowColor = "rgba(246, 198, 91, 0.30)";
        ctx.shadowBlur = isPlaying ? 9 : 0;
        roundedBar(x, y, barWidth, barHeight, Math.min(5, barWidth / 2));
    }

    ctx.shadowBlur = 0;
    animationFrame = requestAnimationFrame(drawSpectrum);
}

mainPlayButton.addEventListener("click", toggleRadio);
dockPlayButton.addEventListener("click", toggleRadio);
identifyButton.addEventListener("click", () => identifyTrack(false));

volumeControl.addEventListener("input", event => {
    const value = Number(event.target.value) / 100;
    audio.volume = value;
    audio.muted = value === 0;
    if (value > 0) lastVolume = value;
    muteButton.textContent = value === 0 ? "🔇" : value < 0.5 ? "🔉" : "🔊";
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

audio.addEventListener("playing", () => {
    setPlayingUI(true);
    spectrumState.textContent = "Spectrum real: frequências ativas";
});

audio.addEventListener("waiting", () => {
    radioStatus.textContent = "A carregar o stream…";
});

audio.addEventListener("stalled", () => {
    radioStatus.textContent = "O stream está a recuperar…";
});

audio.addEventListener("pause", () => {
    if (isPlaying) setPlayingUI(false);
});

audio.addEventListener("error", () => {
    setPlayingUI(false);
    const code = audio.error?.code;
    radioStatus.textContent = `Ligação ao stream interrompida${code ? ` (código ${code})` : ""}`;
    spectrumState.textContent = "Spectrum: sem áudio";
});

window.addEventListener("resize", resizeCanvas);
window.addEventListener("beforeunload", () => {
    clearInterval(identifyTimer);
    cancelAnimationFrame(animationFrame);
    audio.pause();
});

resizeCanvas();
drawSpectrum();
renderAll();
