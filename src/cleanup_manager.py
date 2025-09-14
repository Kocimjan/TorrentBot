"""
Модуль для автоматической очистки временных файлов и контроля дискового пространства
"""
import os
import time
import logging
import threading
from typing import Optional
import shutil

from config import TEMP_DIR, DOWNLOADS_DIR, MAX_DISK_USAGE

logger = logging.getLogger(__name__)


class CleanupManager:
    """Менеджер для автоматической очистки временных файлов"""
    
    def __init__(self):
        self.temp_dir = TEMP_DIR
        self.downloads_dir = DOWNLOADS_DIR
        self.max_disk_usage = MAX_DISK_USAGE
        self.cleanup_thread = None
        self.running = False
        
    def start_cleanup_scheduler(self, interval_hours: int = 2):
        """Запустить планировщик очистки"""
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            logger.warning("Планировщик очистки уже запущен")
            return
        
        self.running = True
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            args=(interval_hours,),
            daemon=True
        )
        self.cleanup_thread.start()
        logger.info(f"Планировщик очистки запущен (интервал: {interval_hours}ч)")
    
    def stop_cleanup_scheduler(self):
        """Остановить планировщик очистки"""
        self.running = False
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
        logger.info("Планировщик очистки остановлен")
    
    def _cleanup_loop(self, interval_hours: int):
        """Основной цикл очистки"""
        interval_seconds = interval_hours * 3600
        
        while self.running:
            try:
                self.cleanup_old_files()
                self.check_disk_usage()
                
                # Ждём до следующей очистки
                for _ in range(interval_seconds):
                    if not self.running:
                        break
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"Ошибка в цикле очистки: {e}")
                time.sleep(60)  # Ждём минуту при ошибке
    
    def cleanup_old_files(self, max_age_hours: int = 24):
        """Очистить старые файлы"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            cleaned_files = 0
            freed_space = 0
            
            # Очищаем временные файлы
            if os.path.exists(self.temp_dir):
                for root, dirs, files in os.walk(self.temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            file_age = current_time - os.path.getmtime(file_path)
                            if file_age > max_age_seconds:
                                file_size = os.path.getsize(file_path)
                                os.remove(file_path)
                                cleaned_files += 1
                                freed_space += file_size
                                logger.debug(f"Удалён старый файл: {file_path}")
                        except (OSError, IOError) as e:
                            logger.warning(f"Не удалось удалить файл {file_path}: {e}")
                    
                    # Удаляем пустые директории
                    for dir_name in dirs:
                        dir_path = os.path.join(root, dir_name)
                        try:
                            if not os.listdir(dir_path):  # Если директория пустая
                                os.rmdir(dir_path)
                                logger.debug(f"Удалена пустая директория: {dir_path}")
                        except (OSError, IOError):
                            pass
            
            if cleaned_files > 0:
                freed_mb = freed_space / (1024 * 1024)
                logger.info(f"Очистка завершена: удалено {cleaned_files} файлов, "
                           f"освобождено {freed_mb:.1f} МБ")
            
        except Exception as e:
            logger.error(f"Ошибка очистки старых файлов: {e}")
    
    def check_disk_usage(self):
        """Проверить использование дискового пространства"""
        try:
            total_usage = self.get_total_disk_usage()
            
            if total_usage > self.max_disk_usage:
                logger.warning(f"Превышен лимит дискового пространства: "
                              f"{total_usage / (1024**3):.1f} ГБ из "
                              f"{self.max_disk_usage / (1024**3):.1f} ГБ")
                
                # Принудительная очистка
                self.force_cleanup()
            
        except Exception as e:
            logger.error(f"Ошибка проверки дискового пространства: {e}")
    
    def get_total_disk_usage(self) -> int:
        """Получить общее использование дискового пространства"""
        total_size = 0
        
        # Считаем размер временных файлов
        if os.path.exists(self.temp_dir):
            total_size += self._get_directory_size(self.temp_dir)
        
        # Считаем размер загрузок
        if os.path.exists(self.downloads_dir):
            total_size += self._get_directory_size(self.downloads_dir)
        
        return total_size
    
    def _get_directory_size(self, directory: str) -> int:
        """Получить размер директории"""
        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, IOError):
                        pass
        except Exception as e:
            logger.error(f"Ошибка получения размера директории {directory}: {e}")
        
        return total_size
    
    def force_cleanup(self):
        """Принудительная очистка при превышении лимита"""
        try:
            logger.info("Запуск принудительной очистки")
            
            # Сначала очищаем старые файлы (более агрессивно)
            self.cleanup_old_files(max_age_hours=1)  # Файлы старше 1 часа
            
            # Если всё ещё превышен лимит, удаляем самые большие файлы
            total_usage = self.get_total_disk_usage()
            if total_usage > self.max_disk_usage:
                self._cleanup_largest_files()
            
        except Exception as e:
            logger.error(f"Ошибка принудительной очистки: {e}")
    
    def _cleanup_largest_files(self):
        """Удалить самые большие файлы для освобождения места"""
        try:
            # Собираем информацию о всех файлах
            files_info = []
            
            for directory in [self.temp_dir, self.downloads_dir]:
                if not os.path.exists(directory):
                    continue
                
                for root, dirs, files in os.walk(directory):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            file_size = os.path.getsize(file_path)
                            file_time = os.path.getmtime(file_path)
                            files_info.append((file_path, file_size, file_time))
                        except (OSError, IOError):
                            pass
            
            # Сортируем по размеру (самые большие сначала)
            files_info.sort(key=lambda x: x[1], reverse=True)
            
            # Удаляем файлы пока не освободим достаточно места
            target_usage = self.max_disk_usage * 0.8  # Оставляем 20% запаса
            current_usage = self.get_total_disk_usage()
            freed_space = 0
            
            for file_path, file_size, file_time in files_info:
                if current_usage - freed_space <= target_usage:
                    break
                
                try:
                    os.remove(file_path)
                    freed_space += file_size
                    logger.info(f"Удалён большой файл: {file_path} "
                               f"({file_size / (1024**2):.1f} МБ)")
                except (OSError, IOError) as e:
                    logger.warning(f"Не удалось удалить файл {file_path}: {e}")
            
            if freed_space > 0:
                logger.info(f"Принудительная очистка освободила "
                           f"{freed_space / (1024**2):.1f} МБ")
            
        except Exception as e:
            logger.error(f"Ошибка удаления больших файлов: {e}")
    
    def cleanup_user_files(self, user_id: int):
        """Очистить файлы конкретного пользователя"""
        try:
            user_temp_dir = os.path.join(self.temp_dir, f"split_{user_id}")
            
            if os.path.exists(user_temp_dir):
                shutil.rmtree(user_temp_dir)
                logger.info(f"Очищены временные файлы пользователя {user_id}")
            
        except Exception as e:
            logger.error(f"Ошибка очистки файлов пользователя {user_id}: {e}")
    
    def get_disk_usage_stats(self) -> dict:
        """Получить статистику использования диска"""
        try:
            temp_size = 0
            downloads_size = 0
            
            if os.path.exists(self.temp_dir):
                temp_size = self._get_directory_size(self.temp_dir)
            
            if os.path.exists(self.downloads_dir):
                downloads_size = self._get_directory_size(self.downloads_dir)
            
            total_size = temp_size + downloads_size
            
            return {
                'temp_size': temp_size,
                'downloads_size': downloads_size,
                'total_size': total_size,
                'max_size': self.max_disk_usage,
                'usage_percent': (total_size / self.max_disk_usage) * 100 if self.max_disk_usage > 0 else 0,
                'free_space': max(0, self.max_disk_usage - total_size)
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики диска: {e}")
            return {}
    
    def format_size(self, size_bytes: int) -> str:
        """Форматировать размер в читаемый вид"""
        if size_bytes == 0:
            return "0 Б"
        
        size_names = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
        i = 0
        while size_bytes >= 1024.0 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"