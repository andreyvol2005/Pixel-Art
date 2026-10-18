/**
 * Сетевой слой: единственное место, где приложение разговаривает с сервером.
 *
 * Раньше внутри app.js лежали и WebSocket, и палитра, и pan/zoom, и отрисовка —
 * 22 функции и 12 переменных в одном файле. Теперь transport знает только про
 * протокол и ничего — про цвета и клетки.
 *
 * Формат сообщений описан в app/schemas.py. У каждого события есть `v`
 * (версия протокола) и `type`, поэтому неизвестное событие можно проигнорировать,
 * а не ловить в общей try/catch.
 */
const PROTOCOL_VERSION = 1;

let socket = null;
let handlers = {};
let backoff = 1000;
const MAX_BACKOFF = 15000;
let closedByUs = false;

function setStatus(text, cls) {
    if (handlers.onStatus) handlers.onStatus(text, cls);
}

/**
 * Подключается и держит соединение живым.
 * @param {object} h - обработчики: onSnapshot, onPixel, onOnline, onClear, onError, onStatus
 */
export function connect(h = {}) {
    handlers = h;
    closedByUs = false;
    open();
}

function open() {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${proto}://${window.location.host}/ws`);

    socket.addEventListener("open", () => {
        backoff = 1000;
        setStatus("онлайн", "online");
    });

    socket.addEventListener("error", () => socket.close());

    socket.addEventListener("close", () => {
        if (closedByUs) return;
        setStatus("переподключение…", "offline");
        // Пауза растёт от секунды до 15: после долгого обрыва не долбим сервер
        setTimeout(open, backoff);
        backoff = Math.min(backoff * 2, MAX_BACKOFF);
    });

    socket.addEventListener("message", (ev) => {
        let event;
        try {
            event = JSON.parse(ev.data);
        } catch (err) {
            return;
        }
        dispatch(event);
    });
}

/** Разбирает входящее событие по типу. Неизвестные типы просто пропускаем. */
function dispatch(event) {
    switch (event?.type) {
        case "snapshot":
            handlers.onSnapshot?.(event.pixels ?? []);
            break;
        case "pixel":
            handlers.onPixel?.(event.x, event.y, event.color);
            break;
        case "online":
            handlers.onOnline?.(event.count);
            break;
        case "clear":
            handlers.onClear?.();
            break;
        case "error":
            handlers.onError?.(event.detail);
            break;
        default:
            // Неизвестный тип или чужая версия протокола — молча пропускаем
            break;
    }
}

function send(command) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ v: PROTOCOL_VERSION, ...command }));
        return true;
    }
    return false;
}

/** Ставит пиксель. Сервер сам разошлёт событие всем, включая нас. */
export function sendPixel(x, y, color) {
    return send({ type: "set_pixel", x, y, color });
}

export function disconnect() {
    closedByUs = true;
    socket?.close();
}