"""
Конфигурация для Userbot.
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class UserbotConfig:
    """Конфигурация для Pyrogram userbot."""
    
    # Telegram API credentials (получить на https://my.telegram.org)
    api_id: Optional[int] = None
    api_hash: Optional[str] = None
    
    # Номер телефона для аутентификации userbot
    phone_number: Optional[str] = None
    
    # ID промежуточного канала/чата для загрузки файлов
    storage_chat_id: Optional[int] = None
    
    # Путь к файлу сессии
    session_name: str = "userbot_session"
    
    # Рабочая директория для сессий
    workdir: str = "sessions"
    
    # Максимальный размер файла для обычной отправки (в байтах)
    max_file_size: int = 2 * 1024 * 1024 * 1024  # 2 ГБ
    
    @classmethod
    def from_env(cls) -> 'UserbotConfig':
        """Создание конфигурации из переменных окружения."""
        return cls(
            api_id=int(os.getenv('USERBOT_API_ID', 24073458)) or None,
            api_hash=os.getenv('USERBOT_API_HASH', '717a1a4a14165bd46f9e066ee639a63f'),
            phone_number=os.getenv('USERBOT_PHONE', '+992004550737'),
            storage_chat_id=int(os.getenv('USERBOT_STORAGE_CHAT_ID', 6690844057)) or None,
            session_name=os.getenv('USERBOT_SESSION_NAME', 'userbot_session'),
            workdir=os.getenv('USERBOT_WORKDIR', 'sessions'),
            max_file_size=int(os.getenv('USERBOT_MAX_FILE_SIZE', 2 * 1024 * 1024 * 1024))
        )
    
    def is_configured(self) -> bool:
        """Проверяет, настроен ли userbot."""
        return all([
            self.api_id,
            self.api_hash,
            self.phone_number,
            self.storage_chat_id
        ])