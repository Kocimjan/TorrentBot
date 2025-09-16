"""
Модуль для отправки файлов с поддержкой userbot для больших файлов.
"""
import os
import asyncio
import logging
from typing import Optional, Callable, Any, Union
from telegram import Bot
from telegram.error import TelegramError

from src.userbot.uploader import get_userbot_file_manager, should_use_userbot
from src.userbot.config import UserbotConfig
from src.file_manager import FileManager

logger = logging.getLogger(__name__)


class SmartFileSender:
    """Умная отправка файлов с автоматическим выбором метода."""
    
    def __init__(self, bot: Bot, file_manager: FileManager):
        """
        Инициализация отправителя файлов.
        
        Args:
            bot: Telegram Bot instance
            file_manager: Файловый менеджер
        """
        self.bot = bot
        self.file_manager = file_manager
        self.userbot_manager = None
        self.userbot_config = UserbotConfig.from_env()
        self.logger = logging.getLogger(f"{__name__}.SmartFileSender")
        self._userbot_initialized = False
        
        # Userbot будет инициализирован при первом использовании
    
    async def _ensure_userbot_initialized(self):
        """Убеждаемся, что userbot инициализирован (ленивая инициализация)."""
        if not self._userbot_initialized:
            await self._init_userbot()
            self._userbot_initialized = True
    
    async def _init_userbot(self):
        """Инициализация userbot менеджера."""
        try:
            if self.userbot_config.is_configured():
                self.logger.info("Инициализация userbot для больших файлов...")
                self.userbot_manager = await get_userbot_file_manager(self.userbot_config)
                
                if self.userbot_manager and self.userbot_manager.is_available():
                    self.logger.info("Userbot успешно инициализирован для больших файлов")
                else:
                    self.logger.warning("Userbot настроен но недоступен (может не хватать прав или база данных недоступна)")
                    self.userbot_manager = None
            else:
                self.logger.info("Userbot не настроен, используем только Bot API (до 50 МБ) и разбивку файлов")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации userbot: {e}")
            self.logger.info("Будем использовать только Bot API (до 50 МБ) и разбивку файлов")
            self.userbot_manager = None
    
    async def send_file(
        self,
        chat_id: Union[int, str],
        file_path: str,
        filename: Optional[str] = None,
        caption: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], Any]] = None
    ) -> bool:
        """
        Отправка файла с автоматическим выбором метода.
        
        Args:
            chat_id: ID чата
            file_path: Путь к файлу
            filename: Имя файла (опционально)
            caption: Подпись к файлу
            progress_callback: Колбэк прогресса
            
        Returns:
            True если файл отправлен успешно
        """
        if not os.path.exists(file_path):
            self.logger.error(f"Файл не найден: {file_path}")
            return False
        
        if filename is None:
            filename = os.path.basename(file_path)
        
        file_size = os.path.getsize(file_path)
        self.logger.info(f"Отправка файла: {filename} ({self._format_size(file_size)})")
        
        # Инициализируем userbot если еще не инициализирован
        await self._ensure_userbot_initialized()
        
        # Определяем метод отправки
        if should_use_userbot(file_path, self.userbot_config) and self.userbot_manager and self.userbot_manager.is_available():
            self.logger.info(f"Используем userbot для отправки большого файла: {filename}")
            return await self._send_via_userbot(chat_id, file_path, filename, caption, progress_callback)
        else:
            # Проверяем лимит Bot API (50 МБ - стандартный лимит Telegram Bot API)
            if file_size > 50 * 1024 * 1024:  # 50 МБ
                self.logger.info(f"Разбиваем файл на части: {filename}")
                return await self._send_via_split(chat_id, file_path, filename, caption)
            else:
                self.logger.info(f"Отправляем файл через Bot API: {filename}")
                return await self._send_via_bot_api(chat_id, file_path, filename, caption)
    
    async def _send_via_userbot(
        self,
        chat_id: Union[int, str],
        file_path: str,
        filename: str,
        caption: Optional[str],
        progress_callback: Optional[Callable[[int, int], Any]]
    ) -> bool:
        """
        Отправка через userbot (для больших файлов).
        
        Args:
            chat_id: ID чата
            file_path: Путь к файлу
            filename: Имя файла
            caption: Подпись
            progress_callback: Колбэк прогресса
            
        Returns:
            True если успешно отправлено
        """
        try:
            self.logger.info(f"Отправка большого файла через userbot: {filename}")
            
            # Отправляем уведомление
            await self.bot.send_message(
                chat_id=chat_id,
                text=f"📦 {filename}\n\n⚠️ Файл превышает лимит Telegram (50 МБ)\n🔄 Загружаю через userbot..."
            )
            
            # Загружаем файл через userbot
            if self.userbot_manager:
                file_id = await self.userbot_manager.upload_large_file(file_path, progress_callback)
            else:
                file_id = None
            
            if not file_id:
                self.logger.error("Не удалось получить file_id от userbot")
                return await self._send_via_split(chat_id, file_path, filename, caption)
            
            # Отправляем файл по file_id
            try:
                await self.bot.send_document(
                    chat_id=chat_id,
                    document=file_id,
                    filename=filename,
                    caption=caption
                )
                
                self.logger.info(f"Файл успешно отправлен через userbot: {filename}")
                return True
                
            except TelegramError as e:
                self.logger.error(f"Ошибка отправки через file_id: {e}")
                # Fallback на разбиение
                return await self._send_via_split(chat_id, file_path, filename, caption)
                
        except Exception as e:
            self.logger.error(f"Ошибка отправки через userbot: {e}")
            # Fallback на разбиение
            return await self._send_via_split(chat_id, file_path, filename, caption)
    
    async def _send_via_bot_api(
        self,
        chat_id: Union[int, str],
        file_path: str,
        filename: str,
        caption: Optional[str]
    ) -> bool:
        """
        Отправка через обычный Bot API.
        
        Args:
            chat_id: ID чата
            file_path: Путь к файлу
            filename: Имя файла
            caption: Подпись
            
        Returns:
            True если успешно отправлено
        """
        try:
            with open(file_path, 'rb') as file:
                await self.bot.send_document(
                    chat_id=chat_id,
                    document=file,
                    filename=filename,
                    caption=caption
                )
            
            self.logger.info(f"Файл успешно отправлен через Bot API: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ошибка отправки через Bot API: {e}")
            return False
    
    async def _send_via_split(
        self,
        chat_id: Union[int, str],
        file_path: str,
        filename: str,
        caption: Optional[str]
    ) -> bool:
        """
        Отправка файла по частям (fallback метод).
        
        Args:
            chat_id: ID чата
            file_path: Путь к файлу
            filename: Имя файла
            caption: Подпись
            
        Returns:
            True если успешно отправлено
        """
        try:
            self.logger.info(f"Разбиваем файл на части: {filename}")
            
            # Уведомляем пользователя
            await self.bot.send_message(
                chat_id=chat_id,
                text=f"📦 {filename}\n\n⚠️ Файл превышает лимит Telegram (50 МБ)\n📄 Разбиваю на части..."
            )
            
            # Используем существующий метод разбиения из FileManager
            if self.file_manager.needs_splitting(file_path):
                parts = self.file_manager.split_file_7z(file_path, os.path.dirname(file_path))
                
                for i, part_path in enumerate(parts, 1):
                    try:
                        part_filename = f"{filename}.part{i}"
                        with open(part_path, 'rb') as part_file:
                            await self.bot.send_document(
                                chat_id=chat_id,
                                document=part_file,
                                filename=part_filename,
                                caption=f"Часть {i}/{len(parts)}" + (f"\n{caption}" if caption and i == 1 else "")
                            )
                        
                        # Удаляем временную часть
                        os.remove(part_path)
                        
                    except Exception as e:
                        self.logger.error(f"Ошибка отправки части {i}: {e}")
                        return False
                
                self.logger.info(f"Файл успешно отправлен по частям: {filename}")
                return True
            else:
                self.logger.error(f"Не удалось разбить файл: {filename}")
                return False
                
        except Exception as e:
            self.logger.error(f"Ошибка разбиения файла: {e}")
            return False
    
    def _format_size(self, size: int) -> str:
        """Форматирование размера файла."""
        size_float = float(size)
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size_float < 1024.0:
                return f"{size_float:.1f} {unit}"
            size_float /= 1024.0
        return f"{size_float:.1f} ТБ"
    
    async def is_userbot_available(self) -> bool:
        """Проверка доступности userbot."""
        await self._ensure_userbot_initialized()
        return self.userbot_manager is not None and self.userbot_manager.is_available()
    
    async def get_userbot_stats(self) -> dict:
        """Получение статистики userbot."""
        await self._ensure_userbot_initialized()
        if self.userbot_manager:
            return self.userbot_manager.get_storage_stats()
        return {}
    
    async def cleanup_userbot_cache(self, max_age_days: int = 30):
        """Очистка кэша userbot."""
        await self._ensure_userbot_initialized()
        if self.userbot_manager:
            await self.userbot_manager.cleanup_old_files(max_age_days)