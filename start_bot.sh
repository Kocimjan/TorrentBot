#!/bin/bash

echo "🤖 Запуск Telegram TorrentBot..."
echo

# Проверяем наличие Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден! Установите Python 3.8+"
    exit 1
fi

# Проверяем наличие requirements.txt
if [ ! -f "requirements.txt" ]; then
    echo "❌ Файл requirements.txt не найден!"
    exit 1
fi

# Устанавливаем зависимости (если нужно)
echo "📦 Проверка зависимостей..."
pip3 install -r requirements.txt --quiet

# Загружаем переменные из .env, если файл существует
if [ -f ".env" ]; then
    set -a
    . ./.env
    set +a
fi

# Проверяем переменную окружения BOT_TOKEN (после .env)
if [ -z "$BOT_TOKEN" ]; then
    echo "⚠️  BOT_TOKEN не установлен!"
    echo "Установите переменную окружения BOT_TOKEN или создайте файл .env"
    echo
fi

echo "🚀 Запуск бота..."
echo "Для остановки нажмите Ctrl+C"
echo

# Запускаем бота
python3 main.py