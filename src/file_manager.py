"""
Модуль для работы с файлами: проверка размера, разбивка, сжатие
"""
import os
import shutil
import logging
import subprocess
from typing import List, Tuple, Optional
import py7zr
import psutil

from config import MAX_FILE_SIZE_DIRECT, SPLIT_CHUNK_SIZE, MAX_DISK_USAGE, TEMP_DIR

logger = logging.getLogger(__name__)


class FileManager:
    """Менеджер для работы с файлами"""
    
    def __init__(self):
        self.temp_dir = TEMP_DIR
        
    def get_disk_usage(self) -> int:
        """Получить текущее использование диска"""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(self.temp_dir):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, IOError):
                    pass
        return total_size
    
    def check_disk_space(self, required_space: int) -> bool:
        """Проверить, достаточно ли места на диске"""
        current_usage = self.get_disk_usage()
        return (current_usage + required_space) <= MAX_DISK_USAGE
    
    def get_file_size(self, filepath: str) -> int:
        """Получить размер файла"""
        try:
            return os.path.getsize(filepath)
        except (OSError, IOError):
            return 0
    
    def needs_splitting(self, filepath: str) -> bool:
        """Проверить, нужно ли разбивать файл"""
        return self.get_file_size(filepath) > MAX_FILE_SIZE_DIRECT
    
    def split_file_7z(self, filepath: str, output_dir: str) -> List[str]:
        """
        Разбить файл на части используя 7z
        Возвращает список путей к частям
        """
        try:
            filename = os.path.basename(filepath)
            archive_path = os.path.join(output_dir, f"{filename}.7z")
            
            # Создаём архив с разбивкой на части
            chunk_size_mb = SPLIT_CHUNK_SIZE // (1024 * 1024)
            
            # Команда для 7z (если установлен системно)
            cmd = [
                "7z", "a", 
                f"-v{chunk_size_mb}m",
                archive_path,
                filepath
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Найти все созданные части
                parts = []
                base_name = f"{filename}.7z"
                for i in range(1, 1000):  # Максимум 1000 частей
                    if i == 1:
                        part_path = os.path.join(output_dir, f"{base_name}.001")
                    else:
                        part_path = os.path.join(output_dir, f"{base_name}.{i:03d}")
                    
                    if os.path.exists(part_path):
                        parts.append(part_path)
                    else:
                        break
                
                return parts
            else:
                logger.error(f"Ошибка 7z: {result.stderr}")
                return self.split_file_py7zr(filepath, output_dir)
                
        except FileNotFoundError:
            logger.warning("7z не найден, используем py7zr")
            return self.split_file_py7zr(filepath, output_dir)
        except Exception as e:
            logger.error(f"Ошибка при разбивке файла через 7z: {e}")
            return []
    
    def split_file_py7zr(self, filepath: str, output_dir: str) -> List[str]:
        """
        Разбить файл на части используя py7zr
        """
        try:
            filename = os.path.basename(filepath)
            file_size = self.get_file_size(filepath)
            
            if file_size <= SPLIT_CHUNK_SIZE:
                # Файл помещается в одну часть
                archive_path = os.path.join(output_dir, f"{filename}.7z")
                with py7zr.SevenZipFile(archive_path, 'w') as archive:
                    archive.write(filepath, filename)
                return [archive_path]
            
            # Разбиваем на части
            parts = []
            part_num = 1
            
            with open(filepath, 'rb') as input_file:
                while True:
                    part_path = os.path.join(output_dir, f"{filename}.7z.{part_num:03d}")
                    
                    # Читаем часть файла
                    chunk = input_file.read(SPLIT_CHUNK_SIZE)
                    if not chunk:
                        break
                    
                    # Создаём временный файл для части
                    temp_part = os.path.join(output_dir, f"temp_part_{part_num}")
                    with open(temp_part, 'wb') as temp_file:
                        temp_file.write(chunk)
                    
                    # Сжимаем часть
                    with py7zr.SevenZipFile(part_path, 'w') as archive:
                        archive.write(temp_part, f"{filename}.part{part_num:03d}")
                    
                    # Удаляем временный файл
                    os.remove(temp_part)
                    
                    parts.append(part_path)
                    part_num += 1
            
            return parts
            
        except Exception as e:
            logger.error(f"Ошибка при разбивке файла через py7zr: {e}")
            return []
    
    def cleanup_directory(self, directory: str, exclude_files: Optional[List[str]] = None):
        """Очистить директорию, исключая указанные файлы"""
        if not os.path.exists(directory):
            return
        
        exclude_files = exclude_files or []
        
        try:
            for filename in os.listdir(directory):
                filepath = os.path.join(directory, filename)
                
                if filename in exclude_files:
                    continue
                
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    logger.debug(f"Удалён файл: {filepath}")
                elif os.path.isdir(filepath):
                    shutil.rmtree(filepath)
                    logger.debug(f"Удалена директория: {filepath}")
                    
        except Exception as e:
            logger.error(f"Ошибка при очистке директории {directory}: {e}")
    
    def get_directory_size(self, directory: str) -> int:
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
            logger.error(f"Ошибка при получении размера директории {directory}: {e}")
        
        return total_size
    
    def format_file_size(self, size_bytes: int) -> str:
        """Форматировать размер файла в читаемый вид"""
        if size_bytes == 0:
            return "0 Б"
        
        size_names = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
        i = 0
        while size_bytes >= 1024.0 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"