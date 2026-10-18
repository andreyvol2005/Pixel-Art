/**
 * Жесты: мышь (рисование / pan / зум колесиком) и тач (рисование / pinch-zoom).
 *
 * Отдельный модуль потому, что это единственное место, где живёт логика
 * «что считать рисованием, а что перемещением». Раньше обработчики дублировались
 * ещё и в buildCanvas(), и в initPanZoom() — событие всплывало в оба, и
 * paintAt вызывался дважды (второй раз выходил рано, но логика была задвоена).
 */
import { state } from "./state.js";
import {
    paintAt,
    paintAtFirstTouch,
    rollbackLastSingleTouchPaint,
    forgetLastTouchPaint,
} from "./canvas.js";
import { pickColorFrom } from "./palette.js";

const MIN_SCALE = 0.1;
const MAX_SCALE = 15;

export function init() {
    const viewport = document.getElementById("viewport");
    const container = document.getElementById("canvasContainer");

    let startX = 0;
    let startY = 0;

    // Переменные pinch-жеста
    let pinchStartDistance = 0;
    let pinchStartScale = 1;
    let pinchStartPointX = 0;
    let pinchStartPointY = 0;
    let pinchStartCenterX = 0;
    let pinchStartCenterY = 0;

    function setTransform() {
        container.style.transform =
            `translate(${state.pointX}px, ${state.pointY}px) scale(${state.scale})`;
    }

    function isCell(target) {
        return target?.classList?.contains("cell");
    }

    /** Единая точка входа: либо пипетка, либо рисование. */
    function paintOrPick(target) {
        if (!isCell(target)) return;
        if (state.eyedropperMode) {
            pickColorFrom(target);
            return;
        }
        paintAt(target);
    }

    // --- Зум колесиком мыши ---
    viewport.addEventListener("wheel", (e) => {
        e.preventDefault();

        // Точка под курсором остаётся на месте
        const xs = (e.clientX - state.pointX) / state.scale;
        const ys = (e.clientY - state.pointY) / state.scale;
        const step = 0.1;
        const delta = -Math.sign(e.deltaY);

        const newScale = clamp(
            state.scale + delta * step * state.scale,
            MIN_SCALE,
            MAX_SCALE
        );

        state.pointX = e.clientX - xs * newScale;
        state.pointY = e.clientY - ys * newScale;
        state.scale = newScale;
        setTransform();
    }, { passive: false });

    // --- Мышь: рисование или pan ---
    viewport.addEventListener("mousedown", (e) => {
        const target = document.elementFromPoint(e.clientX, e.clientY);

        if (!state.drawLocked && isCell(target)) {
            state.isDrawing = true;
            paintOrPick(target);
            return;
        }

        // Кликнули вне холста (или включён замок) — начинаем pan
        state.panning = true;
        startX = e.clientX - state.pointX;
        startY = e.clientY - state.pointY;
        viewport.classList.add("grabbing");
    });

    window.addEventListener("mousemove", (e) => {
        if (!state.panning) {
            if (!state.drawLocked && state.isDrawing) {
                paintOrPick(document.elementFromPoint(e.clientX, e.clientY));
            }
            return;
        }

        e.preventDefault();
        state.pointX = e.clientX - startX;
        state.pointY = e.clientY - startY;
        setTransform();
    });

    window.addEventListener("mouseup", () => {
        state.panning = false;
        state.isDrawing = false;
        viewport.classList.remove("grabbing");
    });

    // --- Тач ---
    viewport.addEventListener("touchstart", (e) => {
        if (e.touches.length === 1) {
            if (state.drawLocked) return;

            const touch = e.touches[0];
            const target = document.elementFromPoint(touch.clientX, touch.clientY);

            if (isCell(target)) {
                state.isDrawing = true;
                if (state.eyedropperMode) {
                    pickColorFrom(target);
                } else {
                    paintAtFirstTouch(target);
                }
            }
        } else if (e.touches.length === 2) {
            e.preventDefault();

            // Второй палец — откатываем то, что успел нарисовать первый
            rollbackLastSingleTouchPaint();

            state.panning = false;
            state.isDrawing = false;

            pinchStartDistance = distance(e.touches);
            pinchStartScale = state.scale;
            pinchStartPointX = state.pointX;
            pinchStartPointY = state.pointY;
            pinchStartCenterX = centerX(e.touches);
            pinchStartCenterY = centerY(e.touches);
        }
    }, { passive: false });

    viewport.addEventListener("touchmove", (e) => {
        if (e.touches.length === 1 && state.isDrawing && !state.drawLocked) {
            e.preventDefault();

            const touch = e.touches[0];
            const target = document.elementFromPoint(touch.clientX, touch.clientY);
            paintOrPick(target);
        } else if (e.touches.length === 2) {
            e.preventDefault();

            const ratio = distance(e.touches) / pinchStartDistance;
            // Коэффициент 0.5 — pinch чувствительнее обычного зума колесом
            const adjustedRatio = 1 + (ratio - 1) * 0.5;
            const newScale = clamp(pinchStartScale * adjustedRatio, MIN_SCALE, MAX_SCALE);

            const canvasX = (pinchStartCenterX - pinchStartPointX) / pinchStartScale;
            const canvasY = (pinchStartCenterY - pinchStartPointY) / pinchStartScale;

            state.scale = newScale;
            state.pointX = centerX(e.touches) - canvasX * newScale;
            state.pointY = centerY(e.touches) - canvasY * newScale;

            setTransform();
        }
    }, { passive: false });

    viewport.addEventListener("touchend", (e) => {
        if (e.touches.length < 2) state.panning = false;
        if (e.touches.length === 0) {
            state.isDrawing = false;
            // Палец оторван полностью — откатывать уже нечего
            forgetLastTouchPaint();
        }
    });

    viewport.addEventListener("touchcancel", () => {
        state.isDrawing = false;
        state.panning = false;
        forgetLastTouchPaint();
    });

    // Начальное позиционирование
    state.pointY = 20;
    setTransform();
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function distance(touches) {
    return Math.hypot(
        touches[0].clientX - touches[1].clientX,
        touches[0].clientY - touches[1].clientY
    );
}

function centerX(touches) {
    return (touches[0].clientX + touches[1].clientX) / 2;
}

function centerY(touches) {
    return (touches[0].clientY + touches[1].clientY) / 2;
}