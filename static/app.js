// ------------------------------------------------------------------ //
//                        Константы клиента                           //
// ------------------------------------------------------------------ //

// Размеры холста — должны совпадать с CANVAS_W / CANVAS_H в app/config.py
const CANVAS_W = 100;
const CANVAS_H = 100;

// Палитра. Первый элемент — цвет по умолчанию (совпадает с CSS .cell).
const PALETTE = [
    "#ffffff", "#000000", "#ff0000", "#00ff00", "#0000ff",
    "#ffff00", "#ff00ff", "#00ffff", "#ff8800", "#8800ff",
];


// ------------------------------------------------------------------ //
//                        Состояние                                   //
// ------------------------------------------------------------------ //

let currentColor = PALETTE[2];
let socket = null;
let isDrawing = false;

const cells = new Map();   // "x,y" → DOM-элемент
const key = (x, y) => `${x},${y}`;


// ------------------------------------------------------------------ //
//                          Палитра                                   //
// ------------------------------------------------------------------ //

function buildPalette() {
    const el = document.getElementById("palette");
    PALETTE.forEach((c, i) => {
        const s = document.createElement("div");
        s.className = "swatch" + (i === 2 ? " active" : "");
        s.style.background = c;
        s.addEventListener("click", () => selectColor(c, s));
        el.appendChild(s);
    });
}

function selectColor(color, el) {
    currentColor = color;
    document.querySelectorAll(".swatch").forEach(s => s.classList.remove("active"));
    if (el) el.classList.add("active");
    document.getElementById("customColor").value = color;
}


// ------------------------------------------------------------------ //
//                            Холст                                   //
// ------------------------------------------------------------------ //

function buildCanvas() {
    const canvas = document.getElementById("canvas");
    canvas.innerHTML = "";
    cells.clear();

    // Создаём все клетки через DocumentFragment — это быстрее,
    // чем 10 000 раз appendChild в живой DOM.
    const frag = document.createDocumentFragment();

    for (let y = 0; y < CANVAS_H; y++) {
        for (let x = 0; x < CANVAS_W; x++) {
            const c = document.createElement("div");
            c.className = "cell";
            c.dataset.x = x;
            c.dataset.y = y;
            frag.appendChild(c);
            cells.set(key(x, y), c);
        }
    }

    canvas.appendChild(frag);

    // --- мышь ---
    canvas.addEventListener("mousedown", e => {
        if (e.target.classList.contains("cell")) {
            isDrawing = true;
            paintAt(e.target);
        }
    });

    canvas.addEventListener("mouseover", e => {
        if (isDrawing && e.target.classList.contains("cell")) {
            paintAt(e.target);
        }
    });

    window.addEventListener("mouseup", () => { isDrawing = false; });

    // --- тач ---
    canvas.addEventListener("touchstart", e => {
        e.preventDefault();
        const t = e.touches[0];
        const el = document.elementFromPoint(t.clientX, t.clientY);
        if (el?.classList.contains("cell")) {
            isDrawing = true;
            paintAt(el);
        }
    }, { passive: false });

    canvas.addEventListener("touchmove", e => {
        e.preventDefault();
        if (!isDrawing) return;
        const t = e.touches[0];
        const el = document.elementFromPoint(t.clientX, t.clientY);
        if (el?.classList.contains("cell")) paintAt(el);
    }, { passive: false });

    canvas.addEventListener("touchend",    () => { isDrawing = false; });
    canvas.addEventListener("touchcancel", () => { isDrawing = false; });
}


// ------------------------------------------------------------------ //
//                          Пиксели                                   //
// ------------------------------------------------------------------ //

function paintAt(cell) {
    const x = +cell.dataset.x;
    const y = +cell.dataset.y;
    if (cell.style.background === currentColor) return;  // уже такой цвет
    applyPixel(x, y, currentColor);
    send([x, y, currentColor]);
}

function applyPixel(x, y, color) {
    const c = cells.get(key(x, y));
    if (c) c.style.background = color;
}


// ------------------------------------------------------------------ //
//                        WebSocket                                   //
// ------------------------------------------------------------------ //

function send(msg) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(msg));
    }
}

function setStatus(text, cls) {
    const el = document.getElementById("status");
    el.textContent = text;
    el.className = cls || "";
}

function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${proto}://${location.host}/ws`);

    socket.addEventListener("open",  () => setStatus("онлайн", "online"));
    socket.addEventListener("error", () => socket.close());
    socket.addEventListener("close", () => {
        setStatus("переподключение…", "offline");
        setTimeout(connect, 1500);
    });

    socket.addEventListener("message", ev => {
        const msg = JSON.parse(ev.data);

        if (Array.isArray(msg)) {
            // один пиксель: [x, y, color]
            applyPixel(msg[0], msg[1], msg[2]);
        } else if (Array.isArray(msg.pixels)) {
            // снапшот: { pixels: [[x,y,color], ...] }
            // сервер шлёт ТОЛЬКО не-белые клетки — белые уже стоят по CSS
            for (const [x, y, color] of msg.pixels) {
                applyPixel(x, y, color);
            }
        }
    });
}


// ------------------------------------------------------------------ //
//                            Init                                    //
// ------------------------------------------------------------------ //

buildPalette();
buildCanvas();

document.getElementById("customColor").addEventListener("input", e => {
    selectColor(e.target.value, null);
});

connect();