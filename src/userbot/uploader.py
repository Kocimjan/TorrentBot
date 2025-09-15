"""
Модуль для загрузки больших файлов через userbot.
"""
import os
import time
import asyncio
import logging
from typing import Optional, Callable, Any
from pathlib import Path

from pyrogram.types import Message
from pyrogram.errors import FloodWait, FilePartMissing, FileMigrate

from .client import UserbotClient, get_userbot_manager
from .config import UserbotConfig
from ..shared.file_id_storage import FileIdStorage, FileUploadRecord


class FileUploader:
    """Загрузчик файлов через userbot."""
    
    def __init__(self, userbot_client: UserbotClient, storage: FileIdStorage):
        """
        Инициализация загрузчика.
        
        Args:
            userbot_client: Клиент userbot
            storage: Хранилище file_id
        """
        self.userbot_client = userbot_client
        self.storage = storage
        self.logger = logging.getLogger(f"{__name__}.FileUploader")
    
    async def upload_file(
        self,
        file_path: str,
        progress_callback: Optional[Callable[[int, int], Any]] = None,
        force_upload: bool = False
    ) -> Optional[FileUploadRecord]:
        """
        Загрузка файла через userbot.
        
        Args:
            file_path: Путь к файлу
            progress_callback: Колбэк для прогресса загрузки
            force_upload: Принудительная загрузка даже если файл уже в кэше
            
        Returns:
            Запись о загруженном файле или None при ошибке
        """
        # Проверяем существование файла
        if not os.path.exists(file_path):
            self.logger.error(f"Файл не найден: {file_path}")
            return None
        
        # Проверяем кэш
        if not force_upload:
            cached_record = self.storage.get_file_id(file_path)
            if cached_record:
                self.logger.info(f"Файл найден в кэше: {file_path}")
                return cached_record
        
        # Получаем клиент
        client = self.userbot_client.get_client()
        if not client:
            self.logger.error("Userbot клиент недоступен")
            return None
        
        # Проверяем промежуточный чат
        if not await self.userbot_client.check_storage_chat():
            self.logger.error("Промежуточный чат недоступен")
            return None
        
        try:
            self.logger.info(f"Начинаем загрузку файла: {file_path}")
            
            # Определяем тип файла
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            
            # Колбэк для отслеживания прогресса
            def upload_progress(current: int, total: int):
                if progress_callback:
                    progress_callback(current, total)
                
                if current % (1024 * 1024 * 10) == 0:  # Каждые 10 МБ
                    progress_percent = (current / total) * 100
                    self.logger.info(f"Загружено: {current}/{total} байт ({progress_percent:.1f}%)")
            
            # Загружаем файл в промежуточный чат
            storage_chat_id = self.userbot_client.config.storage_chat_id
            if not storage_chat_id:
                self.logger.error("ID промежуточного чата не настроен")
                return None
            
            message = await client.send_document(
                chat_id=storage_chat_id,
                document=file_path,
                file_name=file_name,
                progress=upload_progress,
                caption=f"📁 {file_name}\n📐 {self._format_file_size(file_size)}"
            )
            
            # Извлекаем file_id
            if not message:
                self.logger.error("Сообщение не получено")
                return None
                
            file_id = None
            file_unique_id = None
            file_type = None
            
            if hasattr(message, 'document') and message.document:
                file_id = message.document.file_id
                file_unique_id = message.document.file_unique_id
                file_type = "document"
            elif hasattr(message, 'video') and message.video:
                file_id = message.video.file_id
                file_unique_id = message.video.file_unique_id
                file_type = "video"
            elif hasattr(message, 'audio') and message.audio:
                file_id = message.audio.file_id
                file_unique_id = message.audio.file_unique_id
                file_type = "audio"
            else:
                self.logger.error("Неизвестный тип файла в сообщении")
                return None
            
            # Создаём запись
            record = FileUploadRecord(
                file_path=file_path,
                file_id=file_id,
                file_unique_id=file_unique_id,
                file_size=file_size,
                file_type=file_type,
                upload_timestamp=time.time(),
                chat_id=message.chat.id if hasattr(message, 'chat') and message.chat else 0,
                message_id=message.id if hasattr(message, 'id') else 0
            )
            
            # Сохраняем в хранилище
            if self.storage.store_file_id(record):
                self.logger.info(f"Файл успешно загружен: {file_path} -> {file_id}")
                return record
            else:
                self.logger.error("Ошибка сохранения file_id в хранилище")
                return None
                
        except FloodWait as e:
            wait_time = float(e.value) if isinstance(e.value, (int, str)) else 60.0
            self.logger.warning(f"Rate limit, ожидание {wait_time} секунд")
            await asyncio.sleep(wait_time)
            return await self.upload_file(file_path, progress_callback, force_upload)
            
        except (FilePartMissing, FileMigrate) as e:
            self.logger.error(f"Ошибка загрузки файла: {e}")
            return None
            
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при загрузке файла: {e}")
            return None
    
    def _format_file_size(self, size: int) -> str:
        """Форматирование размера файла."""
        size_float = float(size)
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if size_float < 1024.0:
                return f"{size_float:.1f} {unit}"
            size_float /= 1024.0
        return f"{size_float:.1f} ТБ"
    
    async def check_file_exists(self, file_path: str) -> bool:
        """
        Проверка существования файла в кэше.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            True если файл есть в кэше
        """
        return self.storage.file_exists(file_path)
    
    async def get_cached_file_id(self, file_path: str) -> Optional[str]:
        """
        Получение file_id из кэша.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            file_id или None если не найден
        """
        record = self.storage.get_file_id(file_path)
        return record.file_id if record else None


class UserbotFileManager:
    """Менеджер для работы с файлами через userbot."""
    
    def __init__(self, config: Optional[UserbotConfig] = None):
        """
        Инициализация менеджера.
        
        Args:
            config: Конфигурация userbot
        """
        self.config = config or UserbotConfig.from_env()
        self.storage = FileIdStorage()
        self.uploader: Optional[FileUploader] = None
        self.logger = logging.getLogger(f"{__name__}.UserbotFileManager")
    
    async def initialize(self) -> bool:
        """
        Инициализация менеджера.
        
        Returns:
            True если успешно инициализирован
        """
        if not self.config.is_configured():
            self.logger.warning("Userbot не настроен, большие файлы будут недоступны")
            return False
        
        manager = get_userbot_manager(self.config)
        userbot_client = await manager.get_client()
        
        if not userbot_client:
            self.logger.error("Не удалось инициализировать userbot клиент")
            return False
        
        self.uploader = FileUploader(userbot_client, self.storage)
        self.logger.info("UserbotFileManager успешно инициализирован")
        return True
    
    def is_large_file(self, file_path: str) -> bool:
        """
        Проверка, является ли файл большим.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            True если файл превышает лимит Bot API
        """
        if not os.path.exists(file_path):
            return False
        
        file_size = os.path.getsize(file_path)
        return file_size > self.config.max_file_size
    
    def is_available(self) -> bool:
        """
        Проверка доступности userbot.
        
        Returns:
            True если userbot настроен и готов к работе
        """
        return self.uploader is not None
    
    async def upload_large_file(
        self,
        file_path: str,
        progress_callback: Optional[Callable[[int, int], Any]] = None
    ) -> Optional[str]:
        """
        Загрузка большого файла и получение file_id.
        
        Args:
            file_path: Путь к файлу
            progress_callback: Колбэк для прогресса
            
        Returns:
            file_id или None при ошибке
        """
        if not self.uploader:
            self.logger.error("Uploader не инициализирован")
            return None
        
        record = await self.uploader.upload_file(file_path, progress_callback)
        return record.file_id if record else None
    
    async def get_file_id(self, file_path: str) -> Optional[str]:
        """
        Получение file_id файла (из кэша или загрузкой).
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            file_id или None при ошибке
        """
        if not self.uploader:
            return None
        
        return await self.uploader.get_cached_file_id(file_path)
    
    def get_storage_stats(self) -> dict:
        """Получение статистики хранилища."""
        return self.storage.get_stats()
    
    async def cleanup_old_files(self, max_age_days: int = 30):
        """Очистка старых файлов из кэша."""
        self.storage.cleanup_old_records(max_age_days)


# Глобальный экземпляр менеджера
_file_manager: Optional[UserbotFileManager] = None


async def get_userbot_file_manager(config: Optional[UserbotConfig] = None) -> UserbotFileManager:
    """
    Получение глобального экземпляра файлового менеджера.
    
    Args:
        config: Конфигурация userbot
        
    Returns:
        UserbotFileManager
    """
    global _file_manager
    
    if _file_manager is None:
        _file_manager = UserbotFileManager(config)
        await _file_manager.initialize()
    
    return _file_manager


def should_use_userbot(file_path: str, config: Optional[UserbotConfig] = None) -> bool:
    """
    Определение необходимости использования userbot для файла.
    
    Args:
        file_path: Путь к файлу
        config: Конфигурация userbot
        
    Returns:
        True если следует использовать userbot
    """
    if not os.path.exists(file_path):
        return False
    
    if config is None:
        config = UserbotConfig.from_env()
    
    if not config.is_configured():
        return False
    
    file_size = os.path.getsize(file_path)
    return file_size > config.max_file_size