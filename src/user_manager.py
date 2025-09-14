"""
Модуль для управления пользователями и доступом к боту
"""
import sqlite3
import os
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime

from config import LOGS_DIR


class UserManager:
    """Менеджер для управления доступом пользователей"""
    
    def __init__(self):
        self.db_path = os.path.join(LOGS_DIR, 'users.db')
        self.lock = threading.Lock()
        self._init_database()
        
        # Загружаем админов из конфигурации
        self._load_initial_admins()
    
    def _init_database(self):
        """Инициализировать базу данных пользователей"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        role TEXT DEFAULT 'user',
                        added_by INTEGER,
                        added_at TEXT,
                        last_active TEXT,
                        is_active INTEGER DEFAULT 1
                    )
                ''')
                
                # Создаем индексы
                conn.execute('CREATE INDEX IF NOT EXISTS idx_user_role ON users(role)')
                conn.execute('CREATE INDEX IF NOT EXISTS idx_user_active ON users(is_active)')
                
        except Exception as e:
            print(f"Ошибка инициализации БД пользователей: {e}")
    
    def _load_initial_admins(self):
        """Загрузить начальных админов из конфигурации"""
        try:
            from config import AUTHORIZED_USERS
            
            if AUTHORIZED_USERS:
                for user_id in AUTHORIZED_USERS:
                    if not self.user_exists(user_id):
                        self.add_user(
                            user_id=user_id,
                            username="admin",
                            first_name="Admin",
                            role="admin",
                            added_by=user_id
                        )
        except ImportError:
            pass
    
    def user_exists(self, user_id: int) -> bool:
        """Проверить, существует ли пользователь"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
                    return cursor.fetchone() is not None
        except Exception:
            return False
    
    def is_authorized(self, user_id: int) -> bool:
        """Проверить, авторизован ли пользователь"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        'SELECT is_active FROM users WHERE user_id = ?', 
                        (user_id,)
                    )
                    result = cursor.fetchone()
                    return result is not None and result[0] == 1
        except Exception:
            return False
    
    def is_admin(self, user_id: int) -> bool:
        """Проверить, является ли пользователь администратором"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        'SELECT role FROM users WHERE user_id = ? AND is_active = 1', 
                        (user_id,)
                    )
                    result = cursor.fetchone()
                    return result is not None and result[0] == 'admin'
        except Exception:
            return False
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None, 
                 last_name: str = None, role: str = 'user', added_by: int = None) -> bool:
        """Добавить нового пользователя"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute('''
                        INSERT OR REPLACE INTO users 
                        (user_id, username, first_name, last_name, role, added_by, added_at, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    ''', (
                        user_id, username, first_name, last_name, 
                        role, added_by, datetime.now().isoformat()
                    ))
                    return True
        except Exception as e:
            print(f"Ошибка добавления пользователя {user_id}: {e}")
            return False
    
    def remove_user(self, user_id: int, removed_by: int = None) -> bool:
        """Удалить пользователя (деактивировать)"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        'SELECT role FROM users WHERE user_id = ?', 
                        (user_id,)
                    )
                    result = cursor.fetchone()
                    
                    if result and result[0] == 'admin':
                        # Проверяем, что это не последний админ
                        admin_count = conn.execute(
                            'SELECT COUNT(*) FROM users WHERE role = "admin" AND is_active = 1'
                        ).fetchone()[0]
                        
                        if admin_count <= 1:
                            return False  # Нельзя удалить последнего админа
                    
                    conn.execute(
                        'UPDATE users SET is_active = 0 WHERE user_id = ?',
                        (user_id,)
                    )
                    return True
        except Exception as e:
            print(f"Ошибка удаления пользователя {user_id}: {e}")
            return False
    
    def update_last_active(self, user_id: int):
        """Обновить время последней активности пользователя"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        'UPDATE users SET last_active = ? WHERE user_id = ?',
                        (datetime.now().isoformat(), user_id)
                    )
        except Exception:
            pass
    
    def get_user_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить информацию о пользователе"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute(
                        'SELECT * FROM users WHERE user_id = ?', 
                        (user_id,)
                    )
                    result = cursor.fetchone()
                    return dict(result) if result else None
        except Exception:
            return None
    
    def get_all_users(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Получить список всех пользователей"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    
                    query = 'SELECT * FROM users'
                    if active_only:
                        query += ' WHERE is_active = 1'
                    query += ' ORDER BY added_at DESC'
                    
                    cursor = conn.execute(query)
                    return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []
    
    def get_admins(self) -> List[Dict[str, Any]]:
        """Получить список администраторов"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute(
                        'SELECT * FROM users WHERE role = "admin" AND is_active = 1'
                    )
                    return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []
    
    def promote_to_admin(self, user_id: int, promoted_by: int) -> bool:
        """Повысить пользователя до администратора"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        'UPDATE users SET role = "admin" WHERE user_id = ?',
                        (user_id,)
                    )
                    return True
        except Exception as e:
            print(f"Ошибка повышения пользователя {user_id}: {e}")
            return False
    
    def demote_from_admin(self, user_id: int, demoted_by: int) -> bool:
        """Понизить администратора до обычного пользователя"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Проверяем, что это не последний админ
                    admin_count = conn.execute(
                        'SELECT COUNT(*) FROM users WHERE role = "admin" AND is_active = 1'
                    ).fetchone()[0]
                    
                    if admin_count <= 1:
                        return False  # Нельзя понизить последнего админа
                    
                    conn.execute(
                        'UPDATE users SET role = "user" WHERE user_id = ?',
                        (user_id,)
                    )
                    return True
        except Exception as e:
            print(f"Ошибка понижения пользователя {user_id}: {e}")
            return False
    
    def get_user_stats(self) -> Dict[str, int]:
        """Получить статистику пользователей"""
        try:
            with self.lock:
                with sqlite3.connect(self.db_path) as conn:
                    total = conn.execute('SELECT COUNT(*) FROM users WHERE is_active = 1').fetchone()[0]
                    admins = conn.execute('SELECT COUNT(*) FROM users WHERE role = "admin" AND is_active = 1').fetchone()[0]
                    users = total - admins
                    
                    return {
                        'total': total,
                        'admins': admins,
                        'users': users
                    }
        except Exception:
            return {'total': 0, 'admins': 0, 'users': 0}


# Глобальный экземпляр менеджера пользователей
user_manager = UserManager()