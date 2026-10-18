/**
 * Палитра и пипетка.
 *
 * Палитра — это чистый view: рисует свотчи и меняет state.currentColor.
 * Клавиатура/ластик — тоже его дело, логики рисования здесь нет.
 */
import { state } from "./state.js";
import { colorOfCell } from "./canvas.js";

// Первый элемент — ластик. В нём нет цвета, а значит красить им нечем:
// это заглушка на месте «стереть», которая ничего не делает.
export const PALETTE = [
    "eraser",
    "#ffffff",
    "#000000",
    // Тёплые (красный → жёлтый)
    "#ff0000", "#ff3300", "#ff6600", "#ff9900", "#ffcc00", "#ffff00",
    // Холодные (зелёный → синий → фиолетовый)
    "#88ff00", "#00ff00", "#00ff88", "#00ffff", "#0088ff", "#0000ff",
    "#8800ff", "#ff00ff",
];

const BORDER_GREY = "#e8e8e8";

export function init() {
    const root = document.getElementById("palette");

    PALETTE.forEach((color, i) => {
        const swatch = document.createElement("div");
        swatch.className = "swatch" + (i === 0 ? " active" : "");

        if (color === "eraser") {
            swatch.classList.add("eraser");
            swatch.title = "Ластик";
        } else {
            swatch.style.background = color;
        }

        swatch.addEventListener("click", () => selectColor(color, swatch));
        root.appendChild(swatch);
    });

    document.getElementById("customColor").addEventListener("input", (e) => {
        selectColor(e.target.value, null);
    });

    const eyedropper = document.getElementById("eyedropperBtn");
    eyedropper.addEventListener("click", toggleEyedropper);
}

export function selectColor(color, swatchEl) {
    state.currentColor = color;

    document.querySelectorAll(".swatch").forEach((s) => s.classList.remove("active"));
    if (swatchEl) swatchEl.classList.add("active");

    if (color !== "eraser") {
        document.getElementById("customColor").value = color;
    }
}

function setEyedropperMode(on) {
    state.eyedropperMode = on;
    document.getElementById("eyedropperBtn").classList.toggle("active", on);
    document.body.classList.toggle("eyedropper-mode", on);
}

export function toggleEyedropper() {
    setEyedropperMode(!state.eyedropperMode);
}

/** Берёт цвет с клетки и сразу выключает пипетку. */
export function pickColorFrom(cell) {
    let color = colorOfCell(cell);
    // «Шахматный» серый — это подсветка границ, а не цвет холста
    if (color === BORDER_GREY) color = state.config.defaultColor;

    state.currentColor = color;

    document.querySelectorAll(".swatch").forEach((s) => s.classList.remove("active"));
    document.getElementById("customColor").value = color;

    setEyedropperMode(false);
}