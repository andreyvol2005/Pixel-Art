/**
 * Общее состояние клиента.
 *
 * Раньше это были 12 глобальных переменных прямо в app.js. Теперь состояние
 * лежит в одном объекте: его можно целиком посмотреть, подменить в тестах и
 * нельзя случайно «утопить» в замыкании конкретной функции.
 */
export const state = {
    // Приходит с сервера: {width, height, defaultColor}
    // Раньше эти числа были продублированы в app.js, и любая правка на сервере
    // расходилась с клиентом молча.
    config: { width: 400, height: 400, defaultColor: "#ffffff" },

    currentColor: "#ffffff",
    eyedropperMode: false,
    drawLocked: false,
    isDrawing: false,

    // Pan & zoom
    scale: 1,
    pointX: 0,
    pointY: 0,
    panning: false,
};

export function setConfig(config) {
    state.config = {
        width: config.width,
        height: config.height,
        defaultColor: config.default_color ?? config.defaultColor ?? "#ffffff",
    };
}

export function cellKey(x, y) {
    return `${x},${y}`;
}