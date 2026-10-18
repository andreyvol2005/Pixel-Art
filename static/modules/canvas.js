/**
 * Холст: сетка DOM-клеток и рисование.
 *
 * Здесь две разные ответственности, и это осознанно:
 *   * view  — построить сетку, красить клетку;
 *   * use-case «поставить пиксель» — решить, надо ли вообще рисовать.
 * Отправкой занимается transport.js: этот модуль вызывает его напрямую,
 * потому что других каналов связи у клиента нет.
 */
import { state, cellKey } from "./state.js";
import { sendPixel } from "./transport.js";

// "x,y" → DOM-элемент клетки
const cells = new Map();

// Что нарисовал первый палец в текущем касании — нужно для отката,
// когда пользователь ткнёт вторым пальцем (иначе останется случайный пиксель)
let lastSingleTouchPaint = null;

export function init() {
    const { width, height } = state.config;
    const root = document.getElementById("canvas");

    root.innerHTML = "";
    cells.clear();

    // DocumentFragment: 160 000 div'ов одной операцией вставки вместо 160 000
    const frag = document.createDocumentFragment();
    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            const cell = document.createElement("div");
            cell.className = "cell";
            cell.dataset.x = x;
            cell.dataset.y = y;
            frag.appendChild(cell);
            cells.set(cellKey(x, y), cell);
        }
    }
    root.appendChild(frag);
}

/** Красит клетку напрямую. Ничего не отправляет. */
export function applyPixel(x, y, color) {
    const cell = cells.get(cellKey(x, y));
    if (cell) cell.style.background = color;
}

export function clearAll() {
    cells.forEach((cell) => {
        cell.style.background = "";
    });
}

function colorOf(cell) {
    return cell.style.background || state.config.defaultColor;
}

/** Рисование мышью и вторым пальцем. */
export function paintAt(cell) {
    lastSingleTouchPaint = null;

    if (state.eyedropperMode) return;

    // Ластик — это «не рисовать»: он оставлен как заглушка в UI
    if (state.currentColor === "eraser") return;
    if (colorOf(cell) === state.currentColor) return;

    const x = +cell.dataset.x;
    const y = +cell.dataset.y;
    applyPixel(x, y, state.currentColor);
    sendPixel(x, y, state.currentColor);
}

/** Первый палец: запоминаем, что было до рисования, чтобы можно было откатить. */
export function paintAtFirstTouch(cell) {
    if (state.eyedropperMode) return;
    if (state.currentColor === "eraser") return;
    if (colorOf(cell) === state.currentColor) return;

    const x = +cell.dataset.x;
    const y = +cell.dataset.y;
    const prevColor = colorOf(cell);

    applyPixel(x, y, state.currentColor);
    sendPixel(x, y, state.currentColor);

    lastSingleTouchPaint = { x, y, prevColor };
}

export function rollbackLastSingleTouchPaint() {
    if (!lastSingleTouchPaint) return;

    const { x, y, prevColor } = lastSingleTouchPaint;
    lastSingleTouchPaint = null;

    applyPixel(x, y, prevColor);
    sendPixel(x, y, prevColor);   // откат видят все
}

export function forgetLastTouchPaint() {
    lastSingleTouchPaint = null;
}

/** Отдаёт цвет клетки для пипетки. */
export function colorOfCell(cell) {
    return rgbToHex(cell.style.background || state.config.defaultColor);
}

function rgbToHex(rgb) {
    if (rgb.startsWith("#")) return rgb;

    const match = rgb.match(/\d+/g);
    if (!match || match.length < 3) return state.config.defaultColor;

    const r = parseInt(match[0]).toString(16).padStart(2, "0");
    const g = parseInt(match[1]).toString(16).padStart(2, "0");
    const b = parseInt(match[2]).toString(16).padStart(2, "0");
    return `#${r}${g}${b}`;
}