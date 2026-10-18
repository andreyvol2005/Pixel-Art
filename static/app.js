/**
 * Точка входа клиента.
 *
 * Порядок важен: сначала спрашиваем у сервера размеры холста, потом строим
 * сетку (ей нужен размер), потом поднимаем UI и только в конце соединяемся —
 * чтобы первый снимок холста с сервера не пришёл в пустой DOM.
 */
import { setConfig } from "./modules/state.js";
import * as canvas from "./modules/canvas.js";
import * as palette from "./modules/palette.js";
import * as gestures from "./modules/gestures.js";
import * as ui from "./modules/ui.js";
import * as transport from "./modules/transport.js";

async function boot() {
    // 1. Конфигурация с сервера — единственный источник правды про холст
    const response = await fetch("/api/config");
    if (!response.ok) {
        throw new Error(`Не удалось получить конфигурацию: HTTP ${response.status}`);
    }
    setConfig(await response.json());

    // 2. Сетка и интерфейс
    canvas.init();
    palette.init();
    gestures.init();
    ui.init();

    // 3. Соединение
    transport.connect({
        onSnapshot: (pixels) => {
            for (const [x, y, color] of pixels) {
                canvas.applyPixel(x, y, color);
            }
        },
        onPixel: canvas.applyPixel,
        onOnline: ui.setOnline,
        onClear: canvas.clearAll,
        onError: (detail) => ui.setStatus(detail, "error"),
        onStatus: ui.setStatus,
    });
}

boot().catch((err) => {
    console.error(err);
    document.getElementById("status").textContent = "ошибка запуска";
});