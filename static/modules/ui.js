/**
 * Мелкие элементы интерфейса: статус соединения, счётчик онлайна и два
 * тумблера, состояние которых переживает перезагрузку страницы.
 */
import { state } from "./state.js";

const BORDERS_KEY = "pixelCanvas.showBorders";
const LOCK_KEY = "pixelCanvas.drawLocked";

export function init() {
    initBordersToggle();
    initLockToggle();
}

export function setStatus(text, cls) {
    const el = document.getElementById("status");
    el.textContent = text;
    el.className = cls || "";
}

export function setOnline(count) {
    const el = document.getElementById("onlineCount");
    if (el) el.textContent = count;
}

function initBordersToggle() {
    const toggle = document.getElementById("bordersToggle");
    if (!toggle) return;

    const show = localStorage.getItem(BORDERS_KEY) !== "false";
    applyBorders(show);
    toggle.checked = show;

    toggle.addEventListener("change", () => {
        applyBorders(toggle.checked);
        localStorage.setItem(BORDERS_KEY, String(toggle.checked));
    });
}

function applyBorders(show) {
    document.body.classList.toggle("show-borders", show);
}

function initLockToggle() {
    const toggle = document.getElementById("lockToggle");
    if (!toggle) return;

    const locked = localStorage.getItem(LOCK_KEY) === "true";
    applyDrawLock(locked);
    toggle.checked = locked;

    toggle.addEventListener("change", () => {
        applyDrawLock(toggle.checked);
        localStorage.setItem(LOCK_KEY, String(toggle.checked));
    });
}

/** «Замок» — режим «только смотреть»: рисуть нельзя, можно двигать холст. */
function applyDrawLock(locked) {
    state.drawLocked = locked;
}