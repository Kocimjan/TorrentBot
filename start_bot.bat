@echo off
echo 🤖 Запуск Telegram TorrentBot...
echo.

REM Проверяем наличие Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден! Установите Python 3.8+ и добавьте в PATH.
    pause
    exit /b 1
)

REM Проверяем наличие requirements.txt
if not exist "requirements.txt" (
    echo ❌ Файл requirements.txt не найден!
    pause
    exit /b 1
)

REM Устанавливаем зависимости (если нужно)
echo 📦 Проверка зависимостей...
pip install -r requirements.txt --quiet

REM Загружаем переменные из .env, если файл существует
if exist .env (
    for /f "usebackq delims=" %%a in (".env") do set "%%a"
)

REM Проверяем переменную окружения BOT_TOKEN (после .env)
if "%BOT_TOKEN%"=="" (
    echo ⚠️  BOT_TOKEN не установлен!
    echo Установите переменную окружения BOT_TOKEN или создайте файл .env
    echo.
    REM pause
)

echo 🚀 Запуск бота...
echo Для остановки нажмите Ctrl+C
echo.

REM Запускаем бота
python main.py

pause