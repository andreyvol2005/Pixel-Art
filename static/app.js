// ------------------------------------------------------------------ //
//                        Константы клиента                           //
// ------------------------------------------------------------------ //

// Размеры холста — должны совпадать с CANVAS_W / CANVAS_H в app/config.py
const CANVAS_W = 200;
const CANVAS_H = 200;

// Палитра быстрого доступа. Первый элемент — цвет по умолчанию.
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

// Запрет рисования (только pan/zoom) — управляется тумблером "Замок"
let drawLocked = false;

// Что нарисовал первый палец в текущем касании — для отката при появлении второго
let lastSingleTouchPaint = null;   // {x, y, prevColor}

const cells = new Map();   // "x,y" → DOM-элемент
const key = (x, y) => `${x},${y}`;

// Состояние для Pan & Zoom
let scale = 1;
let panning = false;
let pointX = 0;
let pointY = 0;
let startX = 0;
let startY = 0;


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

function setOnline(count) {
    const el = document.getElementById("onlineCount");
    if (el) el.textContent = count;
}

// ------------------------------------------------------------------ //
//                            Холст                                   //
// ------------------------------------------------------------------ //

function buildCanvas() {
    const canvas = document.getElementById("canvas");
    canvas.innerHTML = "";
    cells.clear();

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

    // --- Рисование мышью ---
    canvas.addEventListener("mousedown", e => {
        if (drawLocked) return;
        if (e.target.classList.contains("cell")) {
            isDrawing = true;
            paintAt(e.target);
        }
    });

    canvas.addEventListener("mouseover", e => {
        if (drawLocked) return;
        if (isDrawing && e.target.classList.contains("cell")) {
            paintAt(e.target);
        }
    });

    window.addEventListener("mouseup", () => { isDrawing = false; });
}


// ------------------------------------------------------------------ //
//                          Пиксели                                   //
// ------------------------------------------------------------------ //

function paintAt(cell) {
    // Пользователь двигает палец — это рисование линии, а не подготовка к pinch
    lastSingleTouchPaint = null;

    const x = +cell.dataset.x;
    const y = +cell.dataset.y;
    if (cell.style.background === currentColor) return;

    applyPixel(x, y, currentColor);
    send([x, y, currentColor]);
}

function paintAtFirstTouch(cell) {
    const x = +cell.dataset.x;
    const y = +cell.dataset.y;
    if (cell.style.background === currentColor) return;

    const prevColor = cell.style.background || "#ffffff";

    applyPixel(x, y, currentColor);
    send([x, y, currentColor]);

    // запоминаем — если появится второй палец, откатим
    lastSingleTouchPaint = { x, y, prevColor };
}

function rollbackLastSingleTouchPaint() {
    if (!lastSingleTouchPaint) return;

    const { x, y, prevColor } = lastSingleTouchPaint;
    lastSingleTouchPaint = null;

    applyPixel(x, y, prevColor);
    send([x, y, prevColor]);   // откат видят все
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

    if (msg.action === "clear") {
        cells.forEach(cell => { cell.style.background = "#ffffff"; });
        return;
    }

    if (msg.type === "online") {
        // счётчик онлайн-пользователей
        setOnline(msg.count);
        return;
    }

    if (Array.isArray(msg)) {
        applyPixel(msg[0], msg[1], msg[2]);
    } else if (Array.isArray(msg.pixels)) {
        for (const [x, y, color] of msg.pixels) {
            applyPixel(x, y, color);
        }
    }
});
}


// ------------------------------------------------------------------ //
//                     PAN & ZOOM ЛОГИКА                              //
// ------------------------------------------------------------------ //

function initPanZoom() {
    const viewport = document.getElementById('viewport');
    const container = document.getElementById('canvasContainer');

    function setTransform() {
        container.style.transform = `translate(${pointX}px, ${pointY}px) scale(${scale})`;
    }

    // --- Переменные для pinch-жеста ---
    let pinchStartDistance = 0;
    let pinchStartScale = 1;
    let pinchStartPointX = 0;
    let pinchStartPointY = 0;
    let pinchStartCenterX = 0;
    let pinchStartCenterY = 0;

    // ------------------------------------------------------------------ //
    //                      Зум колесиком мыши (ПК)                       //
    // ------------------------------------------------------------------ //
    viewport.addEventListener('wheel', (e) => {
        e.preventDefault();
        const xs = (e.clientX - pointX) / scale;
        const ys = (e.clientY - pointY) / scale;
        const delta = -Math.sign(e.deltaY);
        const step = 0.1;

        const newScale = Math.min(Math.max(0.5, scale + (delta * step * scale)), 15);

        pointX = e.clientX - xs * newScale;
        pointY = e.clientY - ys * newScale;
        scale = newScale;
        setTransform();
    }, { passive: false });

    // ------------------------------------------------------------------ //
    //                      Мышь: рисование или pan                       //
    // ------------------------------------------------------------------ //
    viewport.addEventListener('mousedown', (e) => {
        const target = document.elementFromPoint(e.clientX, e.clientY);

        if (!drawLocked && target?.classList.contains('cell')) {
            isDrawing = true;
            paintAt(target);
            return;
        }

        // Кликнули вне холста (или замок включён) — начинаем pan
        panning = true;
        startX = e.clientX - pointX;
        startY = e.clientY - pointY;
        viewport.classList.add('grabbing');
    });

    window.addEventListener('mousemove', (e) => {
        if (!panning) {
            if (!drawLocked && isDrawing) {
                const target = document.elementFromPoint(e.clientX, e.clientY);
                if (target?.classList.contains('cell')) {
                    paintAt(target);
                }
            }
            return;
        }
        e.preventDefault();
        pointX = e.clientX - startX;
        pointY = e.clientY - startY;
        setTransform();
    });

    window.addEventListener('mouseup', () => {
        panning = false;
        isDrawing = false;
        viewport.classList.remove('grabbing');
    });

    // ------------------------------------------------------------------ //
    //                        Тач-жесты (мобильные)                       //
    // ------------------------------------------------------------------ //
    viewport.addEventListener('touchstart', (e) => {
        if (e.touches.length === 1) {
            if (drawLocked) return;

            const touch = e.touches[0];
            const target = document.elementFromPoint(touch.clientX, touch.clientY);
            if (target?.classList.contains('cell')) {
                isDrawing = true;
                paintAtFirstTouch(target);
            }
        } else if (e.touches.length === 2) {
            e.preventDefault();

            // Второй палец — откатываем то, что успел нарисовать первый
            rollbackLastSingleTouchPaint();

            panning = false;
            isDrawing = false;

            pinchStartDistance = getDistance(e.touches);
            pinchStartScale = scale;
            pinchStartPointX = pointX;
            pinchStartPointY = pointY;
            pinchStartCenterX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
            pinchStartCenterY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
        }
    }, { passive: false });

    viewport.addEventListener('touchmove', (e) => {
        if (e.touches.length === 1 && isDrawing && !drawLocked) {
            e.preventDefault();

            const touch = e.touches[0];
            const target = document.elementFromPoint(touch.clientX, touch.clientY);
            if (target?.classList.contains('cell')) {
                paintAt(target);   // внутри lastSingleTouchPaint сбросится
            }
        } else if (e.touches.length === 2) {
            e.preventDefault();

            const currentDistance = getDistance(e.touches);
            const currentCenterX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
            const currentCenterY = (e.touches[0].clientY + e.touches[1].clientY) / 2;

            const ratio = currentDistance / pinchStartDistance;
            const adjustedRatio = 1 + (ratio - 1) * 0.5;
            const newScale = Math.min(Math.max(0.5, pinchStartScale * adjustedRatio), 15);

            const canvasX = (pinchStartCenterX - pinchStartPointX) / pinchStartScale;
            const canvasY = (pinchStartCenterY - pinchStartPointY) / pinchStartScale;

            scale = newScale;
            pointX = currentCenterX - (canvasX * scale);
            pointY = currentCenterY - (canvasY * scale);

            setTransform();
        }
    }, { passive: false });

    viewport.addEventListener('touchend', (e) => {
        if (e.touches.length < 2) {
            panning = false;
        }
        if (e.touches.length === 0) {
            isDrawing = false;
            // Палец полностью оторван — забываем, что рисовал первый палец
            lastSingleTouchPaint = null;
        }
    });

    viewport.addEventListener('touchcancel', () => {
        isDrawing = false;
        panning = false;
        lastSingleTouchPaint = null;
    });

    function getDistance(touches) {
        return Math.hypot(
            touches[0].clientX - touches[1].clientX,
            touches[0].clientY - touches[1].clientY
        );
    }

    // Начальное позиционирование
    pointY = 20;
    setTransform();
}


// ------------------------------------------------------------------ //
//                    Тумблер «Границы»                               //
// ------------------------------------------------------------------ //

const BORDERS_KEY = "pixelCanvas.showBorders";

function applyBorders(show) {
    document.body.classList.toggle("show-borders", show);
}

function initBordersToggle() {
    const toggle = document.getElementById("bordersToggle");
    if (!toggle) return;

    const saved = localStorage.getItem(BORDERS_KEY);
    const show = saved === null ? true : saved === "true";

    toggle.checked = show;
    applyBorders(show);

    toggle.addEventListener("change", () => {
        const value = toggle.checked;
        applyBorders(value);
        localStorage.setItem(BORDERS_KEY, String(value));
    });
}


// ------------------------------------------------------------------ //
//                  Тумблер «Замок» (запрет рисования)                //
// ------------------------------------------------------------------ //

const LOCK_KEY = "pixelCanvas.drawLocked";

function applyDrawLock(locked) {
    drawLocked = locked;
}

function initLockToggle() {
    const toggle = document.getElementById("lockToggle");
    if (!toggle) return;

    const saved = localStorage.getItem(LOCK_KEY);
    const locked = saved === "true";

    toggle.checked = locked;
    applyDrawLock(locked);

    toggle.addEventListener("change", () => {
        const value = toggle.checked;
        applyDrawLock(value);
        localStorage.setItem(LOCK_KEY, String(value));
    });
}


// ------------------------------------------------------------------ //
//                            Init                                    //
// ------------------------------------------------------------------ //

buildPalette();
buildCanvas();
initPanZoom();
initBordersToggle();
initLockToggle();

document.getElementById("customColor").addEventListener("input", e => {
    selectColor(e.target.value, null);
});

connect();