"""
Конфигурация для Telegram-бота торрентов
"""
import os
from typing import List

# Базовая директория проекта
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Telegram Bot API
BOT_TOKEN = os.getenv("BOT_TOKEN", "6510728909:AAEZq4Vf35TBTIk_G2hH-RrF4oOYazYs0Ms")

# Авторизованные пользователи (ID Telegram)
AUTHORIZED_USERS: List[int] = [
    # Добавьте свой Telegram ID здесь
    # 123456789,
    906893530,
    6221642254,

]

# Пути к директориям
DOWNLOADS_DIR = os.path.join(BASE_DIR, "downloads")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# Настройки торрент-клиента (qBittorrent)
QBITTORRENT_HOST = "45.153.71.119"
QBITTORRENT_PORT = 8080
QBITTORRENT_USERNAME = "tbate"
QBITTORRENT_PASSWORD = "aqwsderf"

# Настройки Userbot для обхода ограничений
USERBOT_API_ID = os.getenv("USERBOT_API_ID")  # Получить на https://my.telegram.org
USERBOT_API_HASH = os.getenv("USERBOT_API_HASH")  # Получить на https://my.telegram.org
USERBOT_PHONE = os.getenv("USERBOT_PHONE")  # Номер телефона userbot
USERBOT_STORAGE_CHAT_ID = os.getenv("USERBOT_STORAGE_CHAT_ID")  # ID промежуточного чата/канала
USERBOT_SESSION_NAME = os.getenv("USERBOT_SESSION_NAME", "userbot_session")
USERBOT_WORKDIR = os.getenv("USERBOT_WORKDIR", "sessions")
USERBOT_MAX_FILE_SIZE = int(os.getenv("USERBOT_MAX_FILE_SIZE", 50 * 1024 * 1024))  # 50 МБ

# Ограничения размера файлов
MAX_FILE_SIZE_DIRECT = 2 * 1024 * 1024 * 1024  # 2 ГБ
SPLIT_CHUNK_SIZE = 1900 * 1024 * 1024  # 1.9 ГБ для частей
MAX_DISK_USAGE = 50 * 1024 * 1024 * 1024  # 50 ГБ максимальное использование диска

# Настройки логирования
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# Сообщения для пользователей
MESSAGES = {
    "unauthorized": "❌ У вас нет доступа к этому боту.",
    "start": "🤖 Привет! Отправьте мне торрент-файл или magnet-ссылку для скачивания.",
    "processing": "⏳ Обрабатываю торрент...",
    "downloading": "📥 Скачиваю: {name} ({progress}%)",
    "download_complete": "✅ Скачивание завершено: {name}",
    "preparing_files": "📦 Подготавливаю файлы для отправки...",
    "splitting_file": "✂️ Разделяю большой файл: {name}",
    "sending_file": "📤 Отправляю файл: {name}",
    "file_sent": "✅ Файл отправлен: {name}",
    "split_instructions": "📁 Файл был разделён на {parts} частей.\n"
                         "Для восстановления используйте 7-Zip, открыв файл {first_part}",
    "error": "❌ Произошла ошибка: {error}",
    "disk_full": "💾 Недостаточно места на диске. Попробуйте позже.",
    "cleanup": "🗑️ Очищаю временные файлы...",
    "qbittorrent_unavailable": "❌ qBittorrent недоступен. Проверьте подключение.",
    "admin_only": "❌ Только администраторы могут выполнять эту команду.",
    "user_added": "✅ Пользователь {user_id} добавлен с ролью {role}",
    "user_removed": "✅ Пользователь {user_id} удален",
    "user_promoted": "✅ Пользователь {user_id} повышен до администратора",
    "user_demoted": "✅ Пользователь {user_id} понижен до обычного пользователя"
}