"""
Общее хранилище для file_id между ботом и userbot.
"""
import json
import sqlite3
import os
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class FileUploadRecord:
    """Запись о загруженном файле."""
    file_path: str
    file_id: str
    file_unique_id: str
    file_size: int
    file_type: str
    upload_timestamp: float
    chat_id: int
    message_id: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразование в словарь."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FileUploadRecord':
        """Создание из словаря."""
        return cls(**data)


class FileIdStorage:
    """Хранилище file_id для обмена между ботом и userbot."""
    
    def __init__(self, db_path: Optional[str] = None):
        """Инициализация хранилища."""
        if db_path is None:
            # Используем абсолютный путь относительно проекта
            project_root = Path(__file__).parent.parent.parent
            db_path = str(project_root / "logs" / "file_uploads.db")
        
        self.db_path = str(db_path)
        
        # Создаём директорию если не существует
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Инициализируем базу данных
        try:
            self._init_db()
        except Exception as e:
            # Если не удается создать в logs, используем временную директорию
            import tempfile
            temp_dir = tempfile.gettempdir()
            self.db_path = os.path.join(temp_dir, "torrentbot_file_uploads.db")
            print(f"Не удалось создать БД в logs/, используем: {self.db_path}")
            self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_uploads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    file_id TEXT NOT NULL,
                    file_unique_id TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    file_type TEXT NOT NULL,
                    upload_timestamp REAL NOT NULL,
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at REAL DEFAULT (julianday('now'))
                )
            """)
            
            # Создаём индекс для быстрого поиска
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_file_path 
                ON file_uploads(file_path)
            """)
            
            conn.commit()
    
    def store_file_id(self, record: FileUploadRecord) -> bool:
        """
        Сохранение file_id в хранилище.
        
        Args:
            record: Запись о загруженном файле
            
        Returns:
            True если успешно сохранено, False иначе
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO file_uploads 
                    (file_path, file_id, file_unique_id, file_size, file_type, 
                     upload_timestamp, chat_id, message_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    record.file_path,
                    record.file_id,
                    record.file_unique_id,
                    record.file_size,
                    record.file_type,
                    record.upload_timestamp,
                    record.chat_id,
                    record.message_id
                ))
                conn.commit()
                return True
        except Exception as e:
            print(f"Ошибка сохранения file_id: {e}")
            return False
    
    def get_file_id(self, file_path: str) -> Optional[FileUploadRecord]:
        """
        Получение file_id из хранилища.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Запись о файле или None если не найдено
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT file_path, file_id, file_unique_id, file_size, file_type,
                           upload_timestamp, chat_id, message_id
                    FROM file_uploads
                    WHERE file_path = ?
                    ORDER BY upload_timestamp DESC
                    LIMIT 1
                """, (file_path,))
                
                row = cursor.fetchone()
                if row:
                    return FileUploadRecord(*row)
                return None
        except Exception as e:
            print(f"Ошибка получения file_id: {e}")
            return None
    
    def file_exists(self, file_path: str) -> bool:
        """
        Проверка существования файла в хранилище.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            True если файл найден в хранилище
        """
        return self.get_file_id(file_path) is not None
    
    def cleanup_old_records(self, max_age_days: int = 30):
        """
        Удаление старых записей.
        
        Args:
            max_age_days: Максимальный возраст записей в днях
        """
        try:
            cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM file_uploads
                    WHERE upload_timestamp < ?
                """, (cutoff_time,))
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                print(f"Удалено {deleted_count} старых записей из хранилища")
        except Exception as e:
            print(f"Ошибка очистки старых записей: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики хранилища."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_files,
                        SUM(file_size) as total_size,
                        AVG(file_size) as avg_size,
                        MIN(upload_timestamp) as oldest_upload,
                        MAX(upload_timestamp) as newest_upload
                    FROM file_uploads
                """)
                
                row = cursor.fetchone()
                if row:
                    return {
                        'total_files': row[0],
                        'total_size': row[1] or 0,
                        'avg_size': row[2] or 0,
                        'oldest_upload': row[3],
                        'newest_upload': row[4]
                    }
                
                return {
                    'total_files': 0,
                    'total_size': 0,
                    'avg_size': 0,
                    'oldest_upload': None,
                    'newest_upload': None
                }
        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
            return {}