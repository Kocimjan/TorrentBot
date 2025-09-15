"""
Модуль для создания визуального прогресс-бара в Telegram
"""
import time
import math
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class ProgressBar:
    """Класс для создания визуального прогресс-бара"""
    
    def __init__(self, width: int = 20):
        self.width = width
        self.start_time = time.time()
        self.last_update = 0
        
    def create_bar(self, progress: float, show_percentage: bool = True) -> str:
        """
        Создать визуальный прогресс-бар
        
        Args:
            progress: Прогресс от 0 до 100
            show_percentage: Показывать ли процент
        
        Returns:
            Строка с прогресс-баром
        """
        # Ограничиваем прогресс диапазоном 0-100
        progress = max(0, min(100, progress))
        
        # Вычисляем количество заполненных блоков
        filled_length = int(self.width * progress / 100)
        
        # Символы для прогресс-бара
        filled_char = "█"
        partial_chars = ["", "▏", "▎", "▍", "▌", "▋", "▊", "▉"]
        empty_char = "░"
        
        # Создаем основную часть бара
        bar = filled_char * filled_length
        
        # Добавляем частичный блок, если нужно
        if filled_length < self.width:
            partial_progress = (self.width * progress / 100) - filled_length
            partial_index = int(partial_progress * len(partial_chars))
            if partial_index > 0:
                bar += partial_chars[partial_index]
                filled_length += 1
        
        # Добавляем пустые блоки
        bar += empty_char * (self.width - len(bar))
        
        # Добавляем процент, если нужно
        if show_percentage:
            bar = f"[{bar}] {progress:.1f}%"
        else:
            bar = f"[{bar}]"
        
        return bar
    
    def format_speed(self, bytes_per_second: int) -> str:
        """Форматировать скорость загрузки"""
        if bytes_per_second == 0:
            return "0 Б/с"
        
        units = ["Б/с", "КБ/с", "МБ/с", "ГБ/с"]
        unit_index = 0
        speed = float(bytes_per_second)
        
        while speed >= 1024 and unit_index < len(units) - 1:
            speed /= 1024
            unit_index += 1
        
        return f"{speed:.1f} {units[unit_index]}"
    
    def format_size(self, bytes_size: int) -> str:
        """Форматировать размер файла"""
        if bytes_size == 0:
            return "0 Б"
        
        units = ["Б", "КБ", "МБ", "ГБ", "ТБ"]
        unit_index = 0
        size = float(bytes_size)
        
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        
        return f"{size:.1f} {units[unit_index]}"
    
    def format_time(self, seconds: int) -> str:
        """Форматировать время"""
        if seconds <= 0 or seconds > 8640000:  # Больше 100 дней
            return "∞"
        
        if seconds < 60:
            return f"{seconds}с"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}м {seconds % 60}с"
        elif seconds < 86400:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}ч {minutes}м"
        else:
            days = seconds // 86400
            hours = (seconds % 86400) // 3600
            return f"{days}д {hours}ч"
    
    def create_detailed_message(self, info: Dict[str, Any]) -> str:
        """
        Создать подробное сообщение с прогресс-баром
        
        Args:
            info: Информация о торренте
        
        Returns:
            Отформатированное сообщение
        """
        name = info.get('name', 'Неизвестно')
        progress = info.get('progress', 0)
        state = info.get('state', 'unknown')
        size = info.get('size', 0)
        downloaded = info.get('downloaded', 0)
        download_speed = info.get('download_speed', 0)
        upload_speed = info.get('upspeed', 0)
        eta = info.get('eta', 0)
        
        # Создаем прогресс-бар
        progress_bar = self.create_bar(progress)
        
        # Определяем эмодзи состояния
        state_emojis = {
            'downloading': '⬇️',
            'stalledDL': '⏸️',
            'queuedDL': '⏳',
            'uploading': '⬆️',
            'stalledUP': '✅',
            'pausedDL': '⏸️',
            'pausedUP': '⏸️',
            'error': '❌',
            'checkingDL': '🔍',
            'checkingUP': '🔍',
            'queuedUP': '🔄',
            'allocating': '💾',
            'moving': '📁'
        }
        
        state_emoji = state_emojis.get(state, '❓')
        
        # Переводим состояния на русский
        state_translations = {
            'downloading': 'Скачивается',
            'stalledDL': 'Ожидание пиров',
            'queuedDL': 'В очереди',
            'uploading': 'Раздается',
            'stalledUP': 'Завершено',
            'pausedDL': 'Приостановлено',
            'pausedUP': 'Приостановлено',
            'error': 'Ошибка',
            'checkingDL': 'Проверка',
            'checkingUP': 'Проверка',
            'queuedUP': 'В очереди на раздачу',
            'allocating': 'Выделение места',
            'moving': 'Перемещение файлов'
        }
        
        state_text = state_translations.get(state, state)
        
        # Форматируем сообщение
        lines = [
            f"🎬 **{name[:50]}{'...' if len(name) > 50 else ''}**",
            f"",
            f"{progress_bar}",
            f"",
            f"{state_emoji} **Состояние:** {state_text}",
            f"📊 **Размер:** {self.format_size(size)}",
            f"📥 **Скачано:** {self.format_size(downloaded)}"
        ]
        
        # Добавляем скорость, если скачивается
        if download_speed > 0:
            lines.append(f"⚡ **Скорость:** {self.format_speed(download_speed)}")
        
        # Добавляем скорость отдачи, если раздается
        if upload_speed > 0:
            lines.append(f"⬆️ **Отдача:** {self.format_speed(upload_speed)}")
        
        # Добавляем оставшееся время
        if eta > 0 and state in ['downloading', 'stalledDL', 'queuedDL']:
            lines.append(f"⏰ **Осталось:** {self.format_time(eta)}")
        
        # Добавляем время работы
        elapsed = time.time() - self.start_time
        lines.append(f"🕐 **Время:** {self.format_time(int(elapsed))}")
        
        return "\n".join(lines)


class TorrentProgressTracker:
    """Трекер прогресса торрентов с умными обновлениями"""
    
    def __init__(self):
        self.progress_bars: Dict[str, ProgressBar] = {}
        self.last_updates: Dict[str, float] = {}
        self.last_progress: Dict[str, float] = {}
        
    def should_update(self, torrent_hash: str, current_progress: float, force: bool = False) -> bool:
        """
        Определить, нужно ли отправлять обновление
        
        Args:
            torrent_hash: Хэш торрента
            current_progress: Текущий прогресс
            force: Принудительное обновление
        
        Returns:
            True, если нужно отправить обновление
        """
        if force:
            return True
        
        now = time.time()
        last_update = self.last_updates.get(torrent_hash, 0)
        last_progress = self.last_progress.get(torrent_hash, -1)
        
        # Обновляем каждые 30 секунд
        time_threshold = 30
        
        # Или при изменении прогресса на 5%
        progress_threshold = 5.0
        
        # Или при достижении важных этапов (25%, 50%, 75%, 90%, 95%, 99%, 100%)
        important_milestones = [25, 50, 75, 90, 95, 99, 100]
        
        time_passed = now - last_update >= time_threshold
        significant_progress = abs(current_progress - last_progress) >= progress_threshold
        milestone_reached = any(
            last_progress < milestone <= current_progress 
            for milestone in important_milestones
        )
        
        return time_passed or significant_progress or milestone_reached
    
    def get_progress_bar(self, torrent_hash: str) -> ProgressBar:
        """Получить прогресс-бар для торрента"""
        if torrent_hash not in self.progress_bars:
            self.progress_bars[torrent_hash] = ProgressBar()
        return self.progress_bars[torrent_hash]
    
    def update_progress(self, torrent_hash: str, progress: float):
        """Обновить прогресс торрента"""
        self.last_updates[torrent_hash] = time.time()
        self.last_progress[torrent_hash] = progress
    
    def cleanup_torrent(self, torrent_hash: str):
        """Очистить данные торрента"""
        self.progress_bars.pop(torrent_hash, None)
        self.last_updates.pop(torrent_hash, None)
        self.last_progress.pop(torrent_hash, None)
    
    def create_summary_message(self, torrents_info: list) -> str:
        """Создать сводное сообщение о всех активных торрентах"""
        if not torrents_info:
            return "📭 Нет активных торрентов"
        
        lines = ["📊 **Активные торренты:**", ""]
        
        for info in torrents_info:
            name = info.get('name', 'Неизвестно')
            progress = info.get('progress', 0)
            state = info.get('state', 'unknown')
            
            # Короткий прогресс-бар
            short_bar = ProgressBar(width=10).create_bar(progress, show_percentage=False)
            
            # Эмодзи состояния
            state_emoji = {
                'downloading': '⬇️',
                'uploading': '⬆️',
                'stalledUP': '✅',
                'stalledDL': '⏸️',
                'error': '❌'
            }.get(state, '❓')
            
            lines.append(f"{state_emoji} {short_bar} {progress:.0f}% - {name[:30]}{'...' if len(name) > 30 else ''}")
        
        return "\n".join(lines)


# Глобальный экземпляр трекера
progress_tracker = TorrentProgressTracker()