"""
Основной файл Telegram-бота для скачивания торрентов
"""
import os
import sys
import logging
import asyncio
import re
from io import BytesIO
from typing import Optional

from telegram import Update, Document
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ContextTypes
)
from telegram.constants import ParseMode

# Добавляем путь к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from config import (
    BOT_TOKEN, AUTHORIZED_USERS, TEMP_DIR, LOGS_DIR,
    LOG_LEVEL, LOG_FORMAT, MESSAGES
)

# Константы Telegram
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ - лимит Telegram
from src.torrent_client import TorrentClient
from src.file_manager import FileManager
from src.cleanup_manager import CleanupManager
from src.torrent_logger import torrent_logger
from src.user_manager import user_manager
from src.progress_bar import progress_tracker

# Гарантируем наличие директории логов до настройки логгера
os.makedirs(LOGS_DIR, exist_ok=True)

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, 'bot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class TorrentBot:
    """Основной класс Telegram-бота"""
    
    def __init__(self):
        self.torrent_client = TorrentClient()
        self.file_manager = FileManager()
        self.cleanup_manager = CleanupManager()
        self.active_downloads = {}  # {user_id: torrent_hash}
        self.application = None  # Будет установлено в main()
        
        # Запускаем планировщик очистки
        self.cleanup_manager.start_cleanup_scheduler(interval_hours=2)
        
    def check_authorization(self, user_id: int) -> bool:
        """Проверить авторизацию пользователя"""
        # Сначала проверяем через новую систему управления пользователями
        if user_manager.is_authorized(user_id):
            user_manager.update_last_active(user_id)
            return True
        
        # Фолбэк на старую систему (для совместимости)
        return user_id in AUTHORIZED_USERS
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        
        if not self.check_authorization(user_id):
            await update.message.reply_text(MESSAGES["unauthorized"])
            logger.warning(f"Неавторизованный доступ от пользователя {user_id}")
            return
        
        await update.message.reply_text(MESSAGES["start"])
        logger.info(f"Пользователь {user_id} запустил бота")
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик загружаемых документов"""
        user_id = update.effective_user.id
        
        if not self.check_authorization(user_id):
            await update.message.reply_text(MESSAGES["unauthorized"])
            return
        
        document: Document = update.message.document
        
        # Проверяем, что это торрент-файл
        if not document.file_name.endswith('.torrent'):
            await update.message.reply_text("❌ Пожалуйста, отправьте файл с расширением .torrent")
            return
        
        try:
            status_message = await update.message.reply_text("⏳ Обрабатываю торрент-файл...")
            
            # Проверяем подключение к qBittorrent
            if not self.torrent_client.is_connected():
                await status_message.edit_text(
                    "❌ qBittorrent недоступен. Убедитесь, что:\n"
                    "1. qBittorrent запущен\n"
                    "2. Web UI включен в настройках\n"
                    "3. Правильно настроены хост и порт в config.py"
                )
                return
            
            # Логируем начало операции
            user_name = update.effective_user.first_name or "Unknown"
            
            # Скачиваем файл
            file = await context.bot.get_file(document.file_id)
            torrent_data = BytesIO()
            await file.download_to_memory(torrent_data)
            
            # Добавляем торрент в клиент
            torrent_hash = self.torrent_client.add_torrent_file(
                torrent_data.getvalue(), 
                document.file_name
            )
            
            if torrent_hash:
                # Логируем успешное добавление
                operation_id = torrent_logger.log_download_started(
                    user_id, user_name, torrent_hash, document.file_name
                )
                
                self.active_downloads[user_id] = {
                    'torrent_hash': torrent_hash,
                    'operation_id': operation_id
                }
                
                await status_message.edit_text(f"✅ Торрент добавлен! Hash: `{torrent_hash}`")
                
                # Запускаем мониторинг с прогресс-баром
                await self._start_download_monitoring(torrent_hash, update.effective_chat.id)
            else:
                await status_message.edit_text(
                    "❌ Не удалось добавить торрент"
                )
                
        except Exception as e:
            logger.error(f"Ошибка обработки торрент-файла: {e}")
            await update.message.reply_text(
                MESSAGES["error"].format(error=str(e))
            )
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик текстовых сообщений (magnet-ссылки)"""
        user_id = update.effective_user.id
        
        if not self.check_authorization(user_id):
            await update.message.reply_text(MESSAGES["unauthorized"])
            return
        
        text = update.message.text.strip()
        
        # Проверяем, что это magnet-ссылка
        if not text.startswith('magnet:'):
            await update.message.reply_text(
                "❌ Пожалуйста, отправьте magnet-ссылку или торрент-файл"
            )
            return
        
        try:
            status_message = await update.message.reply_text("⏳ Добавляю торрент...")
            
            # Проверяем подключение к qBittorrent
            if not self.torrent_client.is_connected():
                await status_message.edit_text(
                    "❌ qBittorrent недоступен. Убедитесь, что:\n"
                    "1. qBittorrent запущен\n"
                    "2. Web UI включен в настройках\n"
                    "3. Правильно настроены хост и порт в config.py"
                )
                return
            
            # Логируем начало операции
            user_name = update.effective_user.first_name or "Unknown"
            
            # Добавляем magnet-ссылку в клиент
            torrent_hash = self.torrent_client.add_magnet_link(text)
            
            if torrent_hash:
                # Логируем успешное добавление
                operation_id = torrent_logger.log_download_started(
                    user_id, user_name, torrent_hash, "Magnet Link"
                )
                
                self.active_downloads[user_id] = {
                    'torrent_hash': torrent_hash,
                    'operation_id': operation_id
                }
                
                await status_message.edit_text(f"✅ Торрент добавлен! Hash: `{torrent_hash}`")
                
                # Запускаем мониторинг с прогресс-баром
                await self._start_download_monitoring(torrent_hash, update.effective_chat.id)
            else:
                await status_message.edit_text(
                    "❌ Не удалось добавить магнет-ссылку"
                )
                
        except Exception as e:
            logger.error(f"Ошибка обработки magnet-ссылки: {e}")
            await update.message.reply_text(
                MESSAGES["error"].format(error=str(e))
            )
    
    async def _start_download_monitoring(self, torrent_hash: str, chat_id: int):
        """Запустить мониторинг скачивания торрента"""
        # Получаем прогресс-бар для этого торрента
        progress_bar = progress_tracker.get_progress_bar(torrent_hash)
        
        # Создаем очередь для обновлений прогресса
        progress_queue = asyncio.Queue()
        
        def progress_callback(info):
            """Колбэк для отправки обновлений прогресса"""
            try:
                progress = info['progress']
                
                # Проверяем, нужно ли отправлять обновление
                if progress_tracker.should_update(torrent_hash, progress):
                    # Создаем красивое сообщение с прогресс-баром
                    message = progress_bar.create_detailed_message(info)
                    
                    # Добавляем обновление в очередь (без await)
                    try:
                        progress_queue.put_nowait({
                            'message': message,
                            'progress': progress
                        })
                    except asyncio.QueueFull:
                        logger.warning("Очередь прогресса переполнена")
                    
            except Exception as e:
                logger.error(f"Ошибка в progress_callback: {e}")
        
        # Запускаем задачи мониторинга и обработки прогресса
        monitor_task = asyncio.create_task(
            self._monitor_download(torrent_hash, chat_id, progress_callback)
        )
        progress_task = asyncio.create_task(
            self._process_progress_updates(progress_queue, chat_id, torrent_hash)
        )
        
        # Ждем завершения мониторинга и останавливаем обработку прогресса
        await monitor_task
        progress_task.cancel()
    
    async def _process_progress_updates(self, progress_queue: asyncio.Queue, chat_id: int, torrent_hash: str):
        """Обрабатывать обновления прогресса из очереди"""
        try:
            while True:
                try:
                    # Ждем обновление из очереди с таймаутом
                    update_data = await asyncio.wait_for(progress_queue.get(), timeout=1.0)
                    
                    # Отправляем обновление
                    await self._send_progress_update(chat_id, update_data['message'])
                    
                    # Обновляем трекер
                    progress_tracker.update_progress(torrent_hash, update_data['progress'])
                    
                    # Помечаем задачу как выполненную
                    progress_queue.task_done()
                    
                except asyncio.TimeoutError:
                    # Таймаут - продолжаем ждать
                    continue
                    
        except asyncio.CancelledError:
            # Задача отменена - завершаем
            logger.debug("Обработка прогресса остановлена")
        except Exception as e:
            logger.error(f"Ошибка обработки прогресса: {e}")
    
    async def _send_progress_update(self, chat_id: int, message: str):
        """Отправить обновление прогресса с обработкой ошибок"""
        try:
            # Используем Markdown для красивого форматирования
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                disable_notification=True  # Не беспокоим уведомлениями
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить обновление прогресса: {e}")
            # Пробуем отправить без форматирования
            try:
                plain_message = message.replace('**', '').replace('*', '')
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=plain_message,
                    disable_notification=True
                )
            except Exception as e2:
                logger.error(f"Не удалось отправить даже простое сообщение: {e2}")
    
    async def _monitor_download(self, torrent_hash: str, chat_id: int, progress_callback=None):
        """Мониторинг скачивания торрента с прогресс-баром"""
        success = False
        try:
            # Отправляем начальное сообщение
            await self.application.bot.send_message(
                chat_id=chat_id,
                text="🚀 Начинаем мониторинг скачивания..."
            )
            
            # Ждём завершения скачивания с callback для прогресса
            success = await asyncio.get_event_loop().run_in_executor(
                None, 
                self.torrent_client.wait_for_completion, 
                torrent_hash, 
                progress_callback
            )
            
            if success:
                # Получаем финальную информацию о торренте
                info = self.torrent_client.get_torrent_info(torrent_hash)
                if info:
                    # Создаем финальное сообщение с прогресс-баром
                    progress_bar = progress_tracker.get_progress_bar(torrent_hash)
                    final_message = progress_bar.create_detailed_message(info)
                    
                    await self.application.bot.send_message(
                        chat_id=chat_id,
                        text=f"🎉 **Скачивание завершено!**\n\n{final_message}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                
                # Автоматически отправляем файлы после завершения
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text="📤 Подготавливаю файлы для отправки..."
                )
                
                try:
                    await self._send_completed_torrent_files(torrent_hash, chat_id)
                except Exception as e:
                    logger.error(f"Ошибка отправки файлов: {e}")
                    await self.application.bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ Ошибка отправки файлов: {str(e)}\n\nИспользуйте /status для ручной отправки."
                    )
            else:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text="❌ **Ошибка скачивания торрента**\n\nВозможные причины:\n• Нет доступных пиров\n• Ошибка диска\n• Торрент поврежден",
                    parse_mode=ParseMode.MARKDOWN
                )
            
        except Exception as e:
            logger.error(f"Ошибка мониторинга скачивания: {e}")
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=f"❌ **Критическая ошибка мониторинга**\n\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN
            )
        finally:
            # Очищаем данные торрента из трекера
            progress_tracker.cleanup_torrent(torrent_hash)
    
    def _escape_markdown(self, text: str) -> str:
        """Экранировать специальные символы для Markdown"""
        if not text:
            return "Unknown"
        
        # Символы, которые нужно экранировать в Markdown
        escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        
        escaped_text = text
        for char in escape_chars:
            escaped_text = escaped_text.replace(char, f'\\{char}')
        
        return escaped_text
    
    async def _send_completed_torrent_files(self, torrent_hash: str, chat_id: int):
        """Автоматически отправить файлы завершенного торрента"""
        try:
            # Получаем список файлов
            files = self.torrent_client.get_torrent_files(torrent_hash)
            
            if not files:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Файлы торрента не найдены"
                )
                return
            
            # Получаем информацию о торренте
            torrent_info = self.torrent_client.get_torrent_info(torrent_hash)
            torrent_name = torrent_info.get('name', 'Unknown') if torrent_info else 'Unknown'
            
            # Экранируем имя торрента для безопасной отправки
            safe_torrent_name = self._escape_markdown(torrent_name)
            
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=f"📂 **{safe_torrent_name}**\n\n📁 Найдено файлов: {len(files)}\n📤 Начинаю отправку...",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Отправляем файлы
            sent_count = 0
            for i, file_path in enumerate(files, 1):
                filename = os.path.basename(file_path)
                try:
                    file_size = self.file_manager.get_file_size(file_path)
                    
                    # Проверяем размер файла
                    if file_size > MAX_FILE_SIZE:
                        # Файл слишком большой - предлагаем разбить
                        safe_filename_big = self._escape_markdown(filename)
                        await self.application.bot.send_message(
                            chat_id=chat_id,
                            text=f"📦 {safe_filename_big} ({file_size / (1024**2):.1f} МБ)\n\n⚠️ Файл превышает лимит Telegram (50 МБ)\n📄 Разбиваю на части...",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        
                        # Разбиваем и отправляем по частям
                        await self._split_and_send_file_auto(file_path, chat_id)
                        
                    else:
                        # Отправляем файл как есть
                        safe_filename = self._escape_markdown(filename)
                        await self.application.bot.send_message(
                            chat_id=chat_id,
                            text=f"📤 Отправляю файл {i}/{len(files)}: {safe_filename}",
                            parse_mode=ParseMode.MARKDOWN
                        )
                        
                        with open(file_path, 'rb') as file:
                            await self.application.bot.send_document(
                                chat_id=chat_id,
                                document=file,
                                filename=filename
                            )
                    
                    sent_count += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки файла {file_path}: {e}")
                    safe_filename_error = self._escape_markdown(filename)
                    safe_error_text = self._escape_markdown(str(e))
                    await self.application.bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ Ошибка отправки файла {safe_filename_error}: {safe_error_text}",
                        parse_mode=ParseMode.MARKDOWN
                    )
            
            # Итоговое сообщение
            safe_torrent_name_final = self._escape_markdown(torrent_name)
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=f"✅ **Отправка завершена!**\n\n📊 Успешно отправлено: {sent_count}/{len(files)} файлов\n🎉 Торрент **{safe_torrent_name_final}** обработан полностью!",
                parse_mode=ParseMode.MARKDOWN
            )
            
        except Exception as e:
            logger.error(f"Ошибка автоматической отправки файлов: {e}")
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=f"❌ **Ошибка автоматической отправки**\n\n`{str(e)}`\n\nИспользуйте /status для ручной отправки файлов.",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def _split_and_send_file_auto(self, file_path: str, chat_id: int):
        """Разбить большой файл и отправить по частям (автоматически)"""
        try:
            filename = os.path.basename(file_path)
            safe_filename = self._escape_markdown(filename)
            
            # Создаём временную директорию для частей
            temp_dir = os.path.join(TEMP_DIR, f"split_auto_{chat_id}")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Разбиваем файл
            parts = self.file_manager.split_file_7z(file_path, temp_dir)
            
            if not parts:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Не удалось разбить файл {safe_filename}",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            
            # Отправляем каждую часть
            for i, part_path in enumerate(parts, 1):
                part_filename = os.path.basename(part_path)
                safe_part_filename = self._escape_markdown(part_filename)
                
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=f"📤 Отправляю часть {i}/{len(parts)}: {safe_part_filename}",
                    parse_mode=ParseMode.MARKDOWN
                )
                
                with open(part_path, 'rb') as part_file:
                    await self.application.bot.send_document(
                        chat_id=chat_id,
                        document=part_file,
                        filename=part_filename
                    )
            
            # Отправляем инструкции по сборке
            first_part = os.path.basename(parts[0])
            safe_first_part = self._escape_markdown(first_part)
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=f"📋 **Инструкции по сборке файла {safe_filename}:**\n\n"
                     f"1. Скачайте все {len(parts)} частей\n"
                     f"2. Поместите их в одну папку\n"
                     f"3. Откройте первую часть {safe_first_part} с помощью архиватора\n"
                     f"4. Извлеките содержимое",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Очищаем временные файлы
            self.file_manager.cleanup_directory(temp_dir)
            
        except Exception as e:
            try:
                filename = os.path.basename(file_path)
                safe_filename_error = self._escape_markdown(filename)
            except:
                safe_filename_error = "Unknown file"
            safe_error_text = self._escape_markdown(str(e))
            logger.error(f"Ошибка разбивки файла {file_path}: {e}")
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=f"❌ **Ошибка разбивки файла**\n\n{safe_filename_error}: {safe_error_text}",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def _process_downloaded_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                      torrent_hash: str, user_id: int):
        """Обработать скачанные файлы"""
        try:
            await update.message.reply_text(MESSAGES["preparing_files"])
            
            # Получаем список файлов
            files = self.torrent_client.get_torrent_files(torrent_hash)
            
            if not files:
                await update.message.reply_text(
                    MESSAGES["error"].format(error="Не найдены скачанные файлы")
                )
                return
            
            # Обрабатываем каждый файл
            for file_path in files:
                await self._send_file(update, context, file_path, user_id)
            
            # Очищаем торрент
            self.torrent_client.remove_torrent(torrent_hash, delete_files=True)
            
            # Логируем завершение операции
            if user_id in self.active_downloads:
                download_info = self.active_downloads[user_id]
                operation_id = download_info.get('operation_id')
                if operation_id:
                    total_size = sum(self.file_manager.get_file_size(f) for f in files)
                    torrent_logger.log_download_completed(operation_id, total_size)
            
        except Exception as e:
            logger.error(f"Ошибка обработки файлов: {e}")
            await update.message.reply_text(
                MESSAGES["error"].format(error=str(e))
            )
    
    async def _send_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                        file_path: str, user_id: int):
        """Отправить файл пользователю"""
        try:
            file_size = self.file_manager.get_file_size(file_path)
            filename = os.path.basename(file_path)
            
            # Проверяем место на диске
            if not self.file_manager.check_disk_space(file_size * 2):  # *2 для архива
                await update.message.reply_text(MESSAGES["disk_full"])
                return
            
            # Если файл маленький, отправляем напрямую
            if not self.file_manager.needs_splitting(file_path):
                await update.message.reply_text(
                    MESSAGES["sending_file"].format(name=filename)
                )
                
                # Логируем начало отправки
                user_name = update.effective_user.first_name or "Unknown"
                send_operation_id = torrent_logger.log_file_send_started(
                    user_id, user_name, filename, file_size
                )
                
                with open(file_path, 'rb') as file:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=file,
                        filename=filename
                    )
                
                await update.message.reply_text(
                    MESSAGES["file_sent"].format(name=filename)
                )
                
                # Логируем завершение отправки
                torrent_logger.log_file_send_completed(send_operation_id)
            else:
                # Разбиваем большой файл
                await self._split_and_send_file(update, context, file_path, user_id)
                
        except Exception as e:
            logger.error(f"Ошибка отправки файла {file_path}: {e}")
            await update.message.reply_text(
                MESSAGES["error"].format(error=f"Ошибка отправки файла: {str(e)}")
            )
    
    async def _split_and_send_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  file_path: str, user_id: int):
        """Разбить большой файл и отправить по частям"""
        try:
            filename = os.path.basename(file_path)
            
            await update.message.reply_text(
                MESSAGES["splitting_file"].format(name=filename)
            )
            
            # Логируем начало разбивки
            user_name = update.effective_user.first_name or "Unknown"
            file_size = self.file_manager.get_file_size(file_path)
            split_operation_id = torrent_logger.log_file_split_started(
                user_id, user_name, filename, file_size
            )
            
            # Создаём временную директорию для частей
            temp_dir = os.path.join(TEMP_DIR, f"split_{user_id}")
            os.makedirs(temp_dir, exist_ok=True)
            
            # Разбиваем файл
            parts = self.file_manager.split_file_7z(file_path, temp_dir)
            
            if not parts:
                torrent_logger.log_error(split_operation_id, "Не удалось разбить файл")
                await update.message.reply_text(
                    MESSAGES["error"].format(error="Не удалось разбить файл")
                )
                return
            
            # Логируем завершение разбивки
            torrent_logger.log_file_split_completed(split_operation_id, len(parts))
            
            # Отправляем каждую часть
            for i, part_path in enumerate(parts, 1):
                part_filename = os.path.basename(part_path)
                part_size = self.file_manager.get_file_size(part_path)
                
                await update.message.reply_text(
                    f"📤 Отправляю часть {i}/{len(parts)}: {part_filename}"
                )
                
                # Логируем отправку части
                part_send_id = torrent_logger.log_file_send_started(
                    user_id, user_name, part_filename, part_size
                )
                
                with open(part_path, 'rb') as part_file:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=part_file,
                        filename=part_filename
                    )
                
                # Логируем завершение отправки части
                torrent_logger.log_file_send_completed(part_send_id)
            
            # Отправляем инструкции по сборке
            first_part = os.path.basename(parts[0])
            await update.message.reply_text(
                MESSAGES["split_instructions"].format(
                    parts=len(parts),
                    first_part=first_part
                )
            )
            
            # Очищаем временные файлы
            self.file_manager.cleanup_directory(temp_dir)
            
        except Exception as e:
            logger.error(f"Ошибка разбивки файла {file_path}: {e}")
            await update.message.reply_text(
                MESSAGES["error"].format(error=f"Ошибка разбивки файла: {str(e)}")
            )
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статус всех торрентов с прогресс-барами"""
        user_id = update.effective_user.id
        
        if not self.check_authorization(user_id):
            await update.message.reply_text(MESSAGES["unauthorized"])
            return
        
        try:
            if not self.torrent_client.is_connected():
                await update.message.reply_text("❌ **Нет подключения к qBittorrent**", parse_mode=ParseMode.MARKDOWN)
                return
            
            # Получаем все торренты
            torrents = self.torrent_client.client.torrents_info()
            
            if not torrents:
                await update.message.reply_text("📭 **Нет активных торрентов**", parse_mode=ParseMode.MARKDOWN)
                return
            
            # Группируем торренты по состояниям
            downloading = []
            completed = []
            uploading = []
            paused = []
            errors = []
            
            for torrent in torrents:
                info = self.torrent_client.get_torrent_info(torrent.hash)
                if info:
                    state = info['state']
                    if state in ['downloading', 'stalledDL', 'queuedDL']:
                        downloading.append(info)
                    elif state in ['uploading', 'stalledUP', 'queuedUP']:
                        if info['progress'] >= 100:
                            completed.append(info)
                        else:
                            uploading.append(info)
                    elif state in ['pausedDL', 'pausedUP']:
                        paused.append(info)
                    elif state in ['error', 'missingFiles']:
                        errors.append(info)
            
            # Создаем сообщение со статистикой
            messages = []
            
            if downloading:
                messages.append("⬇️ **Скачиваются:**")
                for info in downloading:
                    progress_bar = progress_tracker.get_progress_bar(info['hash'])
                    progress_line = progress_bar.create_bar(info['progress'])
                    speed = progress_bar.format_speed(info['download_speed'])
                    name = info['name'][:30] + ('...' if len(info['name']) > 30 else '')
                    messages.append(f"`{progress_line}`")
                    messages.append(f"📁 {name}")
                    messages.append(f"⚡ {speed}")
                    messages.append("")
            
            if completed:
                messages.append("✅ **Завершены:**")
                for info in completed:
                    name = info['name'][:40] + ('...' if len(info['name']) > 40 else '')
                    size = progress_tracker.get_progress_bar('').format_size(info['size'])
                    ratio = info.get('ratio', 0)
                    messages.append(f"📁 {name}")
                    messages.append(f"💾 {size} | 📤 Рейтинг: {ratio:.2f}")
                    messages.append("")
            
            if uploading:
                messages.append("⬆️ **Раздаются:**")
                for info in uploading:
                    name = info['name'][:40] + ('...' if len(info['name']) > 40 else '')
                    up_speed = progress_tracker.get_progress_bar('').format_speed(info.get('upspeed', 0))
                    messages.append(f"📁 {name}")
                    messages.append(f"⚡ {up_speed}")
                    messages.append("")
            
            if paused:
                messages.append("⏸️ **Приостановлены:**")
                for info in paused:
                    name = info['name'][:40] + ('...' if len(info['name']) > 40 else '')
                    messages.append(f"📁 {name} ({info['progress']:.1f}%)")
            
            if errors:
                messages.append("❌ **Ошибки:**")
                for info in errors:
                    name = info['name'][:40] + ('...' if len(info['name']) > 40 else '')
                    messages.append(f"� {name}")
            
            # Отправляем сообщение частями, если оно слишком длинное
            full_message = "\n".join(messages)
            
            if len(full_message) > 4000:  # Лимит Telegram ~4096 символов
                # Разбиваем на части
                parts = []
                current_part = []
                current_length = 0
                
                for line in messages:
                    line_length = len(line) + 1  # +1 для \n
                    if current_length + line_length > 3500:  # Оставляем запас
                        parts.append("\n".join(current_part))
                        current_part = [line]
                        current_length = line_length
                    else:
                        current_part.append(line)
                        current_length += line_length
                
                if current_part:
                    parts.append("\n".join(current_part))
                
                # Отправляем части
                for i, part in enumerate(parts):
                    header = f"📊 **Статус торрентов** (часть {i+1}/{len(parts)})\n\n" if len(parts) > 1 else "📊 **Статус торрентов**\n\n"
                    await update.message.reply_text(header + part, parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(f"📊 **Статус торрентов**\n\n{full_message}", parse_mode=ParseMode.MARKDOWN)
        
        except Exception as e:
            logger.error(f"Ошибка получения статуса: {e}")
            await update.message.reply_text(f"❌ **Ошибка получения статуса**\n\n`{str(e)}`", parse_mode=ParseMode.MARKDOWN)
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для получения статистики бота (только для авторизованных пользователей)"""
        user_id = update.effective_user.id
        
        if not self.check_authorization(user_id):
            await update.message.reply_text(MESSAGES["unauthorized"])
            return
        
        try:
            # Получаем статистику операций
            stats = torrent_logger.get_operation_stats(days=7)
            
            # Получаем статистику диска
            disk_stats = self.cleanup_manager.get_disk_usage_stats()
            
            stats_text = "📊 **Статистика бота (7 дней):**\n\n"
            
            # Операции
            total_ops = stats.get('total_operations', 0)
            stats_text += f"🔄 Всего операций: {total_ops}\n"
            
            if stats.get('operations_by_type'):
                stats_text += "\n📈 По типам:\n"
                for op_type, count in stats['operations_by_type'].items():
                    stats_text += f"  • {op_type}: {count}\n"
            
            if stats.get('operations_by_status'):
                stats_text += "\n📋 По статусам:\n"
                for status, count in stats['operations_by_status'].items():
                    stats_text += f"  • {status}: {count}\n"
            
            # Передано данных
            total_bytes = stats.get('total_transferred_bytes', 0)
            if total_bytes > 0:
                total_gb = total_bytes / (1024**3)
                stats_text += f"\n💾 Передано: {total_gb:.2f} ГБ\n"
            
            # Использование диска
            stats_text += f"\n💿 **Диск:**\n"
            stats_text += f"Использовано: {self.cleanup_manager.format_size(disk_stats.get('total_size', 0))}\n"
            stats_text += f"Лимит: {self.cleanup_manager.format_size(disk_stats.get('max_size', 0))}\n"
            stats_text += f"Процент: {disk_stats.get('usage_percent', 0):.1f}%"
            
            await update.message.reply_text(stats_text, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            await update.message.reply_text(
                MESSAGES["error"].format(error="Не удалось получить статистику")
            )
    
    async def cleanup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для принудительной очистки (только для авторизованных пользователей)"""
        user_id = update.effective_user.id
        
        if not self.check_authorization(user_id):
            await update.message.reply_text(MESSAGES["unauthorized"])
            return
        
        try:
            await update.message.reply_text("🗑️ Запуск очистки...")
            
            # Принудительная очистка
            self.cleanup_manager.force_cleanup()
            
            # Очистка старых логов
            torrent_logger.cleanup_old_logs(days=30)
            
            # Получаем новую статистику диска
            disk_stats = self.cleanup_manager.get_disk_usage_stats()
            
            result_text = f"✅ Очистка завершена!\n\n"
            result_text += f"💿 Использование диска:\n"
            result_text += f"Использовано: {self.cleanup_manager.format_size(disk_stats.get('total_size', 0))}\n"
            result_text += f"Процент: {disk_stats.get('usage_percent', 0):.1f}%"
            
            await update.message.reply_text(result_text)
            
        except Exception as e:
            logger.error(f"Ошибка очистки: {e}")
            await update.message.reply_text(
                MESSAGES["error"].format(error="Ошибка при очистке")
            )
    
    async def add_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для добавления пользователя (только для админов)"""
        user_id = update.effective_user.id
        
        if not user_manager.is_admin(user_id):
            await update.message.reply_text("❌ Только администраторы могут добавлять пользователей.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "📝 Использование: /adduser <user_id> [role]\n"
                "Роли: user (по умолчанию), admin\n"
                "Пример: /adduser 123456789 user"
            )
            return
        
        try:
            target_user_id = int(context.args[0])
            role = context.args[1] if len(context.args) > 1 else 'user'
            
            if role not in ['user', 'admin']:
                await update.message.reply_text("❌ Неверная роль. Используйте: user или admin")
                return
            
            if user_manager.user_exists(target_user_id):
                await update.message.reply_text(f"❌ Пользователь {target_user_id} уже существует.")
                return
            
            success = user_manager.add_user(
                user_id=target_user_id,
                role=role,
                added_by=user_id
            )
            
            if success:
                role_emoji = "👑" if role == "admin" else "👤"
                await update.message.reply_text(
                    f"✅ Пользователь {target_user_id} добавлен с ролью {role_emoji} {role}"
                )
            else:
                await update.message.reply_text("❌ Ошибка при добавлении пользователя.")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный ID пользователя. Используйте числовой ID.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def remove_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для удаления пользователя (только для админов)"""
        user_id = update.effective_user.id
        
        if not user_manager.is_admin(user_id):
            await update.message.reply_text("❌ Только администраторы могут удалять пользователей.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "📝 Использование: /removeuser <user_id>\n"
                "Пример: /removeuser 123456789"
            )
            return
        
        try:
            target_user_id = int(context.args[0])
            
            if target_user_id == user_id:
                await update.message.reply_text("❌ Вы не можете удалить самого себя.")
                return
            
            if not user_manager.user_exists(target_user_id):
                await update.message.reply_text(f"❌ Пользователь {target_user_id} не найден.")
                return
            
            success = user_manager.remove_user(target_user_id, removed_by=user_id)
            
            if success:
                await update.message.reply_text(f"✅ Пользователь {target_user_id} удален.")
            else:
                await update.message.reply_text("❌ Ошибка при удалении пользователя (возможно, это последний админ).")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный ID пользователя. Используйте числовой ID.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def list_users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для просмотра списка пользователей (только для админов)"""
        user_id = update.effective_user.id
        
        if not user_manager.is_admin(user_id):
            await update.message.reply_text("❌ Только администраторы могут просматривать список пользователей.")
            return
        
        try:
            users = user_manager.get_all_users()
            stats = user_manager.get_user_stats()
            
            if not users:
                await update.message.reply_text("📭 Нет зарегистрированных пользователей.")
                return
            
            message = f"👥 **Пользователи бота** (всего: {stats['total']})\n\n"
            
            # Группируем по ролям
            admins = [u for u in users if u['role'] == 'admin']
            regular_users = [u for u in users if u['role'] == 'user']
            
            if admins:
                message += "👑 **Администраторы:**\n"
                for user in admins:
                    name = user['first_name'] or "Неизвестно"
                    username = f"@{user['username']}" if user['username'] else ""
                    message += f"• {user['user_id']} - {name} {username}\n"
                message += "\n"
            
            if regular_users:
                message += "👤 **Пользователи:**\n"
                for user in regular_users:
                    name = user['first_name'] or "Неизвестно"
                    username = f"@{user['username']}" if user['username'] else ""
                    message += f"• {user['user_id']} - {name} {username}\n"
            
            await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка получения списка пользователей: {str(e)}")
    
    async def promote_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для повышения пользователя до админа (только для админов)"""
        user_id = update.effective_user.id
        
        if not user_manager.is_admin(user_id):
            await update.message.reply_text("❌ Только администраторы могут повышать пользователей.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "📝 Использование: /promote <user_id>\n"
                "Пример: /promote 123456789"
            )
            return
        
        try:
            target_user_id = int(context.args[0])
            
            if not user_manager.user_exists(target_user_id):
                await update.message.reply_text(f"❌ Пользователь {target_user_id} не найден.")
                return
            
            if user_manager.is_admin(target_user_id):
                await update.message.reply_text(f"❌ Пользователь {target_user_id} уже является администратором.")
                return
            
            success = user_manager.promote_to_admin(target_user_id, promoted_by=user_id)
            
            if success:
                await update.message.reply_text(f"✅ Пользователь {target_user_id} повышен до администратора.")
            else:
                await update.message.reply_text("❌ Ошибка при повышении пользователя.")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный ID пользователя. Используйте числовой ID.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def demote_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда для понижения админа до пользователя (только для админов)"""
        user_id = update.effective_user.id
        
        if not user_manager.is_admin(user_id):
            await update.message.reply_text("❌ Только администраторы могут понижать других админов.")
            return
        
        if not context.args:
            await update.message.reply_text(
                "📝 Использование: /demote <user_id>\n"
                "Пример: /demote 123456789"
            )
            return
        
        try:
            target_user_id = int(context.args[0])
            
            if target_user_id == user_id:
                await update.message.reply_text("❌ Вы не можете понизить самого себя.")
                return
            
            if not user_manager.user_exists(target_user_id):
                await update.message.reply_text(f"❌ Пользователь {target_user_id} не найден.")
                return
            
            if not user_manager.is_admin(target_user_id):
                await update.message.reply_text(f"❌ Пользователь {target_user_id} не является администратором.")
                return
            
            success = user_manager.demote_from_admin(target_user_id, demoted_by=user_id)
            
            if success:
                await update.message.reply_text(f"✅ Пользователь {target_user_id} понижен до обычного пользователя.")
            else:
                await update.message.reply_text("❌ Ошибка при понижении (возможно, это последний админ).")
                
        except ValueError:
            await update.message.reply_text("❌ Неверный ID пользователя. Используйте числовой ID.")
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда помощи"""
        user_id = update.effective_user.id
        
        if not self.check_authorization(user_id):
            await update.message.reply_text(MESSAGES["unauthorized"])
            return
        
        help_text = "🤖 **Команды бота:**\n\n"
        help_text += "📥 **Основные команды:**\n"
        help_text += "/start - Начать работу с ботом\n"
        help_text += "/status - Статус активных загрузок\n"
        help_text += "/stats - Статистика бота\n"
        help_text += "/cleanup - Очистка временных файлов\n"
        help_text += "/help - Показать эту справку\n\n"
        
        if user_manager.is_admin(user_id):
            help_text += "👑 **Команды администратора:**\n"
            help_text += "/adduser <id> [role] - Добавить пользователя\n"
            help_text += "/removeuser <id> - Удалить пользователя\n"
            help_text += "/listusers - Список пользователей\n"
            help_text += "/promote <id> - Повысить до админа\n"
            help_text += "/demote <id> - Понизить до пользователя\n\n"
        
        help_text += "📁 **Использование:**\n"
        help_text += "• Отправьте .torrent файл\n"
        help_text += "• Отправьте magnet-ссылку\n\n"
        help_text += "Файлы > 2 ГБ будут автоматически разбиты на части."
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    def run(self):
        """Запустить бота"""
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN не установлен!")
            return
        
        if not AUTHORIZED_USERS:
            logger.warning("AUTHORIZED_USERS пуст - никто не сможет использовать бота!")
        
        # Создаём приложение
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        
        # Устанавливаем application в TorrentBot для отправки сообщений
        self.application = app
        
        # Добавляем обработчики
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("status", self.status_command))
        app.add_handler(CommandHandler("stats", self.stats_command))
        app.add_handler(CommandHandler("cleanup", self.cleanup_command))
        app.add_handler(CommandHandler("help", self.help_command))
        
        # Команды управления пользователями (только для админов)
        app.add_handler(CommandHandler("adduser", self.add_user_command))
        app.add_handler(CommandHandler("removeuser", self.remove_user_command))
        app.add_handler(CommandHandler("listusers", self.list_users_command))
        app.add_handler(CommandHandler("promote", self.promote_user_command))
        app.add_handler(CommandHandler("demote", self.demote_user_command))
        
        app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        
        logger.info("Бот запущен")
        print("🤖 Telegram-бот торрентов запущен!")
        print("📝 Для работы бота необходимо:")
        print("1. Установить BOT_TOKEN в переменной окружения")
        print("2. Добавить свой Telegram ID в AUTHORIZED_USERS в config.py")
        print("3. Настроить и запустить qBittorrent с Web UI")
        
        # Запускаем бота
        app.run_polling()


if __name__ == "__main__":
    # Создаём необходимые директории
    for directory in [TEMP_DIR, LOGS_DIR]:
        os.makedirs(directory, exist_ok=True)
    
    # Запускаем бота
    bot = TorrentBot()
    bot.run()