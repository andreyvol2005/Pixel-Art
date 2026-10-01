# Pixel-Art Online
<img width="958" height="764" alt="image" src="https://github.com/user-attachments/assets/9a215cc2-f71e-41b5-ba54-de5bf1360088" />


Совместный пиксель-арт холст в реальном времени. Без регистрации. 100 × 100 клеток.

---

## Установка

### 1. Docker Desktop

Установи и запусти: https://www.docker.com/products/docker-desktop/

**Windows:** если при запуске ошибка «WSL not installed» — в PowerShell от админа:

```
wsl --install
```

Перезагрузи ПК.

Дождись в Docker Desktop надписи **Engine running**. Проверь:

```
docker ps
```

### 2. Виртуальное окружение

**Windows:**

```
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Зависимости

```
pip install -r requirements.txt
pip install greenlet
```

### 4. Postgres и Redis

Из корня проекта:

```
docker compose up -d
```

### 5. Сервер

```
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Дождись `Application startup complete.` Терминал не закрывай.

### 6. Открыть

```
http://localhost:8000
```

---

## Доступ с других устройств в той же Wi-Fi

1. Узнай IP:

   **Windows:** `ipconfig` → строка IPv4-адрес.

   **macOS:** `ipconfig getifaddr en0`

2. Разреши порт 8000 в брандмауэре.

   **Windows** (PowerShell от админа):

   ```
   New-NetFirewallRule -DisplayName "Pixel Canvas" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Any
   ```

   **macOS:** при первом запуске uvicorn нажми **Allow** в системном окне.

3. Отправь другу:

   ```
   http://<твой-IP>:8000
   ```

   Друг должен быть в той же Wi-Fi сети.
