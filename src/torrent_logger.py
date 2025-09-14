"""
Модуль для детального логирования операций бота
"""
import os
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import sqlite3
import threading

from config import LOGS_DIR


@dataclass
class TorrentOperation:
    """Класс для хранения информации об операции с торрентом"""
    user_id: int
    user_name: str
    operation_type: str  # 'download', 'upload', 'split', 'send'
    torrent_hash: Optional[str]
    torrent_name: Optional[str]
    file_name: Optional[str]
    file_size: Optional[int]
    status: str  # 'started', 'in_progress', 'completed', 'failed'
    timestamp: str
    details: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None


class TorrentLogger:
    """Расширенный логгер для операций с торрентами"""
    
    def __init__(self):
        self.db_path = os.path.join(LOGS_DIR, 'torrent_operations.db')
        self.lock = threading.Lock()
        self._init_database()
        
        # Настраиваем обычный логгер
        self.logger = logging.getLogger('torrent_operations')
        self.logger.setLevel(logging.INFO)
        
        # Файловый обработчик для операций
        operations_handler = logging.FileHandler(
            os.path.join(LOGS_DIR, 'operations.log'),
            encoding='utf-8'
        )
        operations_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        self.logger.addHandler(operations_handler)
    
    def _init_database(self):
        """Инициализировать базу данных для логов"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS operations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        user_name TEXT NOT NULL,
                        operation_type TEXT NOT NULL,
                        torrent_hash TEXT,
                        torrent_name TEXT,
                        file_name TEXT,
                        file_size INTEGER,
                        status TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        details TEXT,
                        error_message TEXT
                    )
                ''')
                
                # Индексы для быстрого поиска
                conn.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON operations(user_id)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON operations(timestamp)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_status ON operations(status)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_operation_type ON operations(operation_type)')
                
        except Exception as e:
            self.logger.error(f"Ошибка инициализации БД логов: {e}")
    
    def log_operation(self, operation: TorrentOperation) -> int:
        """Записать операцию в лог"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute('''
                        INSERT INTO operations 
                        (user_id, user_name, operation_type, torrent_hash, torrent_name, 
                         file_name, file_size, status, timestamp, details, error_message)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        operation.user_id,
                        operation.user_name,
                        operation.operation_type,
                        operation.torrent_hash,
                        operation.torrent_name,
                        operation.file_name,
                        operation.file_size,
                        operation.status,
                        operation.timestamp,
                        json.dumps(operation.details) if operation.details else None,
                        operation.error_message
                    ))
                    
                    operation_id = cursor.lastrowid
                    
                    # Логируем в обычный лог
                    log_message = (
                        f"[{operation.operation_type.upper()}] "
                        f"User {operation.user_id} ({operation.user_name}) - "
                        f"{operation.status}: {operation.file_name or operation.torrent_name}"
                    )
                    
                    if operation.status == 'failed' and operation.error_message:
                        log_message += f" - Error: {operation.error_message}"
                    
                    self.logger.info(log_message)
                    
                    return operation_id
                    
        except Exception as e:
            self.logger.error(f"Ошибка записи операции в БД: {e}")
            return -1
    
    def update_operation_status(self, operation_id: int, status: str, 
                              error_message: Optional[str] = None,
                              details: Optional[Dict[str, Any]] = None):
        """Обновить статус операции"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute('''
                        UPDATE operations 
                        SET status = ?, error_message = ?, details = ?
                        WHERE id = ?
                    ''', (
                        status,
                        error_message,
                        json.dumps(details) if details else None,
                        operation_id
                    ))
                    
        except Exception as e:
            self.logger.error(f"Ошибка обновления статуса операции {operation_id}: {e}")
    
    def get_user_operations(self, user_id: int, limit: int = 10) -> list:
        """Получить последние операции пользователя"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT * FROM operations 
                    WHERE user_id = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (user_id, limit))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            self.logger.error(f"Ошибка получения операций пользователя {user_id}: {e}")
            return []
    
    def get_operation_stats(self, days: int = 7) -> Dict[str, Any]:
        """Получить статистику операций за последние дни"""
        try:
            from_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            with sqlite3.connect(self.db_path) as conn:
                # Общее количество операций
                total_ops = conn.execute('''
                    SELECT COUNT(*) FROM operations 
                    WHERE timestamp >= datetime('now', '-{} days')
                '''.format(days)).fetchone()[0]
                
                # Статистика по типам операций
                ops_by_type = conn.execute('''
                    SELECT operation_type, COUNT(*) as count
                    FROM operations 
                    WHERE timestamp >= datetime('now', '-{} days')
                    GROUP BY operation_type
                '''.format(days)).fetchall()
                
                # Статистика по статусам
                ops_by_status = conn.execute('''
                    SELECT status, COUNT(*) as count
                    FROM operations 
                    WHERE timestamp >= datetime('now', '-{} days')
                    GROUP BY status
                '''.format(days)).fetchall()
                
                # Самые активные пользователи
                active_users = conn.execute('''
                    SELECT user_id, user_name, COUNT(*) as count
                    FROM operations 
                    WHERE timestamp >= datetime('now', '-{} days')
                    GROUP BY user_id, user_name
                    ORDER BY count DESC
                    LIMIT 5
                '''.format(days)).fetchall()
                
                # Общий размер переданных файлов
                total_size = conn.execute('''
                    SELECT SUM(file_size) FROM operations 
                    WHERE timestamp >= datetime('now', '-{} days')
                    AND file_size IS NOT NULL
                    AND status = 'completed'
                '''.format(days)).fetchone()[0] or 0
                
                return {
                    'total_operations': total_ops,
                    'operations_by_type': {row[0]: row[1] for row in ops_by_type},
                    'operations_by_status': {row[0]: row[1] for row in ops_by_status},
                    'active_users': [{'user_id': row[0], 'user_name': row[1], 'count': row[2]} 
                                   for row in active_users],
                    'total_transferred_bytes': total_size,
                    'period_days': days
                }
                
        except Exception as e:
            self.logger.error(f"Ошибка получения статистики: {e}")
            return {}
    
    def log_download_started(self, user_id: int, user_name: str, 
                           torrent_hash: str, torrent_name: str) -> int:
        """Логировать начало скачивания торрента"""
        operation = TorrentOperation(
            user_id=user_id,
            user_name=user_name,
            operation_type='download',
            torrent_hash=torrent_hash,
            torrent_name=torrent_name,
            file_name=None,
            file_size=None,
            status='started',
            timestamp=datetime.now().isoformat()
        )
        return self.log_operation(operation)
    
    def log_download_progress(self, operation_id: int, progress: float, 
                            download_speed: int, eta: int):
        """Логировать прогресс скачивания"""
        details = {
            'progress': progress,
            'download_speed': download_speed,
            'eta': eta
        }
        self.update_operation_status(operation_id, 'in_progress', details=details)
    
    def log_download_completed(self, operation_id: int, file_size: int):
        """Логировать завершение скачивания"""
        details = {'final_file_size': file_size}
        self.update_operation_status(operation_id, 'completed', details=details)
    
    def log_file_split_started(self, user_id: int, user_name: str, 
                             file_name: str, file_size: int) -> int:
        """Логировать начало разбивки файла"""
        operation = TorrentOperation(
            user_id=user_id,
            user_name=user_name,
            operation_type='split',
            torrent_hash=None,
            torrent_name=None,
            file_name=file_name,
            file_size=file_size,
            status='started',
            timestamp=datetime.now().isoformat()
        )
        return self.log_operation(operation)
    
    def log_file_split_completed(self, operation_id: int, parts_count: int):
        """Логировать завершение разбивки файла"""
        details = {'parts_count': parts_count}
        self.update_operation_status(operation_id, 'completed', details=details)
    
    def log_file_send_started(self, user_id: int, user_name: str, 
                            file_name: str, file_size: int) -> int:
        """Логировать начало отправки файла"""
        operation = TorrentOperation(
            user_id=user_id,
            user_name=user_name,
            operation_type='send',
            torrent_hash=None,
            torrent_name=None,
            file_name=file_name,
            file_size=file_size,
            status='started',
            timestamp=datetime.now().isoformat()
        )
        return self.log_operation(operation)
    
    def log_file_send_completed(self, operation_id: int):
        """Логировать завершение отправки файла"""
        self.update_operation_status(operation_id, 'completed')
    
    def log_error(self, operation_id: int, error_message: str):
        """Логировать ошибку операции"""
        self.update_operation_status(operation_id, 'failed', error_message=error_message)
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """Очистить старые логи"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    deleted_count = conn.execute('''
                        DELETE FROM operations 
                        WHERE timestamp < datetime('now', '-{} days')
                    '''.format(days_to_keep)).rowcount
                    
                    if deleted_count > 0:
                        self.logger.info(f"Удалено {deleted_count} старых записей из логов")
                        
        except Exception as e:
            self.logger.error(f"Ошибка очистки старых логов: {e}")
    
    def export_logs_to_json(self, output_file: str, days: int = 7) -> bool:
        """Экспортировать логи в JSON файл"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT * FROM operations 
                    WHERE timestamp >= datetime('now', '-{} days')
                    ORDER BY timestamp DESC
                '''.format(days))
                
                operations = [dict(row) for row in cursor.fetchall()]
                
                # Парсим JSON в details
                for op in operations:
                    if op['details']:
                        try:
                            op['details'] = json.loads(op['details'])
                        except:
                            pass
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(operations, f, indent=2, ensure_ascii=False)
                
                self.logger.info(f"Логи экспортированы в {output_file}")
                return True
                
        except Exception as e:
            self.logger.error(f"Ошибка экспорта логов: {e}")
            return False


# Глобальный экземпляр логгера
torrent_logger = TorrentLogger()