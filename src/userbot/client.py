"""
Pyrogram клиент для userbot функциональности.
"""
import os
import asyncio
import logging
from typing import Optional
from pathlib import Path

from pyrogram.client import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneNumberInvalid

from .config import UserbotConfig


class UserbotClient:
    """Pyrogram клиент для userbot."""
    
    def __init__(self, config: UserbotConfig):
        """
        Инициализация клиента.
        
        Args:
            config: Конфигурация userbot
        """
        self.config = config
        self.client: Optional[Client] = None
        self.is_authenticated = False
        
        # Настройка логгинга
        self.logger = logging.getLogger(f"{__name__}.UserbotClient")
        
        # Создаём директорию для сессий
        os.makedirs(self.config.workdir, exist_ok=True)
    
    async def initialize(self) -> bool:
        """
        Инициализация и аутентификация клиента.
        
        Returns:
            True если успешно инициализирован
        """
        if not self.config.is_configured():
            self.logger.error("Userbot не настроен. Проверьте конфигурацию.")
            return False
        
        try:
            # Создаём клиента
            session_path = os.path.join(self.config.workdir, self.config.session_name)
            
            if not all([self.config.api_id, self.config.api_hash, self.config.phone_number]):
                self.logger.error("Отсутствуют обязательные параметры userbot")
                return False
            
            self.client = Client(
                session_path,
                api_id=self.config.api_id or 0,
                api_hash=self.config.api_hash or "",
                phone_number=self.config.phone_number or "",
                workdir=self.config.workdir
            )
            
            # Подключаемся
            await self.client.start()
            
            # Проверяем аутентификацию
            me = await self.client.get_me()
            self.is_authenticated = True
            
            self.logger.info(f"Userbot успешно инициализирован для пользователя: {me.first_name}")
            return True
            
        except SessionPasswordNeeded:
            self.logger.error("Требуется двухфакторная аутентификация. Настройте userbot вручную.")
            return False
        except (PhoneCodeInvalid, PhoneNumberInvalid) as e:
            self.logger.error(f"Ошибка аутентификации: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Ошибка инициализации userbot: {e}")
            return False
    
    async def stop(self):
        """Остановка клиента."""
        if self.client:
            try:
                await self.client.stop()
                self.is_authenticated = False
                self.logger.info("Userbot остановлен")
            except Exception as e:
                self.logger.error(f"Ошибка остановки userbot: {e}")
    
    async def test_connection(self) -> bool:
        """
        Тестирование подключения.
        
        Returns:
            True если подключение работает
        """
        if not self.client or not self.is_authenticated:
            return False
        
        try:
            me = await self.client.get_me()
            self.logger.info(f"Тест подключения успешен: {me.first_name}")
            return True
        except Exception as e:
            self.logger.error(f"Тест подключения неуспешен: {e}")
            return False
    
    async def check_storage_chat(self) -> bool:
        """
        Проверка доступности промежуточного чата/канала.
        
        Returns:
            True если чат доступен
        """
        if not self.client or not self.is_authenticated:
            return False
        
        try:
            if not self.config.storage_chat_id:
                self.logger.error("ID промежуточного чата не настроен")
                return False
                
            chat = await self.client.get_chat(self.config.storage_chat_id)
            chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', 'Unknown')
            self.logger.info(f"Промежуточный чат доступен: {chat_name}")
            return True
        except Exception as e:
            self.logger.error(f"Промежуточный чат недоступен: {e}")
            return False
    
    def get_client(self) -> Optional[Client]:
        """
        Получение экземпляра клиента.
        
        Returns:
            Pyrogram Client или None
        """
        return self.client if self.is_authenticated else None


class UserbotManager:
    """Менеджер для управления userbot клиентом."""
    
    def __init__(self, config: UserbotConfig):
        """
        Инициализация менеджера.
        
        Args:
            config: Конфигурация userbot
        """
        self.config = config
        self.client_instance: Optional[UserbotClient] = None
        self.logger = logging.getLogger(f"{__name__}.UserbotManager")
    
    async def get_client(self) -> Optional[UserbotClient]:
        """
        Получение инициализированного клиента.
        
        Returns:
            UserbotClient или None если не удалось инициализировать
        """
        if self.client_instance and self.client_instance.is_authenticated:
            return self.client_instance
        
        # Создаём новый клиент
        self.client_instance = UserbotClient(self.config)
        
        if await self.client_instance.initialize():
            return self.client_instance
        
        self.client_instance = None
        return None
    
    async def stop_client(self):
        """Остановка клиента."""
        if self.client_instance:
            await self.client_instance.stop()
            self.client_instance = None
    
    def is_available(self) -> bool:
        """
        Проверка доступности userbot.
        
        Returns:
            True если userbot настроен и доступен
        """
        return self.config.is_configured()


# Глобальный экземпляр менеджера
_manager: Optional[UserbotManager] = None


def get_userbot_manager(config: Optional[UserbotConfig] = None) -> UserbotManager:
    """
    Получение глобального экземпляра менеджера userbot.
    
    Args:
        config: Конфигурация (используется только при первом вызове)
        
    Returns:
        UserbotManager
    """
    global _manager
    
    if _manager is None:
        if config is None:
            config = UserbotConfig.from_env()
        _manager = UserbotManager(config)
    
    return _manager


async def cleanup_userbot():
    """Очистка ресурсов userbot."""
    global _manager
    
    if _manager:
        await _manager.stop_client()
        _manager = None