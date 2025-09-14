"""
Модуль для работы с торрент-клиентом qBittorrent
"""
import os
import time
import logging
from typing import Optional, Dict, Any, List
import qbittorrentapi
import tempfile
import requests

from config import (
    QBITTORRENT_HOST, QBITTORRENT_PORT, 
    QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD,
    DOWNLOADS_DIR
)

logger = logging.getLogger(__name__)


class TorrentClient:
    """Клиент для работы с qBittorrent"""
    
    def __init__(self):
        self.client = None
        self.downloads_dir = DOWNLOADS_DIR
        self._connect()
    
    def _connect(self):
        """Подключиться к qBittorrent"""
        try:
            self.client = qbittorrentapi.Client(
                host=QBITTORRENT_HOST,
                port=QBITTORRENT_PORT,
                username=QBITTORRENT_USERNAME,
                password=QBITTORRENT_PASSWORD,
                VERIFY_WEBUI_CERTIFICATE=False,
                REQUESTS_ARGS={'timeout': (3, 10)}  # connection timeout, read timeout
            )
            
            # Проверяем подключение
            self.client.auth_log_in()
            logger.info("Успешно подключён к qBittorrent")
            
            # Настраиваем папку загрузок
            self._setup_downloads_directory()
            
        except qbittorrentapi.exceptions.LoginFailed:
            logger.error("Ошибка авторизации в qBittorrent. Проверьте логин и пароль.")
            self.client = None
        except qbittorrentapi.exceptions.APIConnectionError:
            logger.error(f"Не удается подключиться к qBittorrent по адресу {QBITTORRENT_HOST}:{QBITTORRENT_PORT}")
            logger.error("Убедитесь, что:")
            logger.error("1. qBittorrent запущен")
            logger.error("2. Web UI включен в настройках")
            logger.error("3. Правильно указаны хост и порт в config.py")
            self.client = None
        except Exception as e:
            logger.error(f"Ошибка подключения к qBittorrent: {e}")
            self.client = None
    
    def _setup_downloads_directory(self):
        """Настроить папку загрузок"""
        try:
            if not os.path.exists(self.downloads_dir):
                os.makedirs(self.downloads_dir)
            
            # Устанавливаем папку по умолчанию
            self.client.app_set_preferences({
                "save_path": self.downloads_dir
            })
            
        except Exception as e:
            logger.error(f"Ошибка настройки папки загрузок: {e}")
    
    def is_connected(self) -> bool:
        """Проверить подключение к клиенту"""
        try:
            if self.client is None:
                return False
            
            # Простая проверка - получаем версию
            self.client.app_version()
            return True
            
        except Exception:
            return False
    
    def add_torrent_file(self, torrent_data: bytes, filename: str) -> Optional[str]:
        """
        Добавить торрент из файла
        Возвращает hash торрента или None при ошибке
        """
        try:
            if not self.is_connected():
                self._connect()
                
            if not self.is_connected():
                raise Exception("Не удалось подключиться к qBittorrent")
            
            # Сохраняем торрент во временный файл
            with tempfile.NamedTemporaryFile(suffix='.torrent', delete=False) as temp_file:
                temp_file.write(torrent_data)
                temp_file_path = temp_file.name
            
            try:
                # Добавляем торрент
                result = self.client.torrents_add(
                    torrent_files=temp_file_path,
                    save_path=self.downloads_dir
                )
                
                # Получаем hash добавленного торрента
                if result == "Ok.":
                    # Ждём немного, чтобы торрент появился в списке
                    time.sleep(1)
                    
                    # Ищем торрент по имени файла
                    torrents = self.client.torrents_info()
                    for torrent in torrents:
                        if torrent.name in filename or filename in torrent.name:
                            logger.info(f"Торрент добавлен: {torrent.name} ({torrent.hash})")
                            return torrent.hash
                    
                    # Если не нашли по имени, берём последний добавленный
                    if torrents:
                        latest_torrent = max(torrents, key=lambda t: t.added_on)
                        logger.info(f"Торрент добавлен: {latest_torrent.name} ({latest_torrent.hash})")
                        return latest_torrent.hash
                
                return None
                
            finally:
                # Удаляем временный файл
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Ошибка добавления торрент-файла: {e}")
            return None
    
    def add_magnet_link(self, magnet_link: str) -> Optional[str]:
        """
        Добавить торрент по magnet-ссылке
        Возвращает hash торрента или None при ошибке
        """
        try:
            if not self.is_connected():
                self._connect()
                
            if not self.is_connected():
                raise Exception("Не удалось подключиться к qBittorrent")
            
            # Добавляем магнет-ссылку
            result = self.client.torrents_add(
                urls=magnet_link,
                save_path=self.downloads_dir
            )
            
            if result == "Ok.":
                # Ждём, чтобы торрент появился в списке
                time.sleep(2)
                
                # Пытаемся найти добавленный торрент
                torrents = self.client.torrents_info()
                if torrents:
                    # Берём последний добавленный
                    latest_torrent = max(torrents, key=lambda t: t.added_on)
                    logger.info(f"Магнет-ссылка добавлена: {latest_torrent.name} ({latest_torrent.hash})")
                    return latest_torrent.hash
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка добавления magnet-ссылки: {e}")
            return None
    
    def get_torrent_info(self, torrent_hash: str) -> Optional[Dict[str, Any]]:
        """Получить информацию о торренте"""
        try:
            if not self.is_connected():
                return None
            
            torrents = self.client.torrents_info(torrent_hashes=torrent_hash)
            if torrents:
                torrent = torrents[0]
                return {
                    'name': torrent.name,
                    'state': torrent.state,
                    'progress': torrent.progress * 100,  # Переводим в проценты
                    'size': torrent.size,
                    'downloaded': torrent.downloaded,
                    'download_speed': torrent.dlspeed,
                    'eta': torrent.eta,
                    'files_count': torrent.num_files
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка получения информации о торренте: {e}")
            return None
    
    def wait_for_completion(self, torrent_hash: str, progress_callback=None) -> bool:
        """
        Ждать завершения скачивания торрента
        progress_callback: функция для отправки обновлений прогресса
        """
        try:
            logger.info(f"Ожидание завершения торрента {torrent_hash}")
            
            while True:
                info = self.get_torrent_info(torrent_hash)
                
                if info is None:
                    logger.error("Торрент не найден")
                    return False
                
                state = info['state']
                progress = info['progress']
                
                # Отправляем обновление прогресса
                if progress_callback:
                    progress_callback(info)
                
                # Проверяем состояние
                if state in ['uploading', 'stalledUP', 'queuedUP']:
                    # Скачивание завершено
                    logger.info(f"Торрент {torrent_hash} скачан успешно")
                    return True
                elif state in ['error', 'missingFiles']:
                    # Ошибка скачивания
                    logger.error(f"Ошибка скачивания торрента {torrent_hash}: {state}")
                    return False
                
                # Ждём 5 секунд перед следующей проверкой
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"Ошибка ожидания завершения торрента: {e}")
            return False
    
    def get_torrent_files(self, torrent_hash: str) -> List[str]:
        """Получить список файлов торрента"""
        try:
            if not self.is_connected():
                return []
            
            # Получаем информацию о торренте
            torrents = self.client.torrents_info(torrent_hashes=torrent_hash)
            if not torrents:
                return []
            
            torrent = torrents[0]
            
            # Получаем список файлов
            files = self.client.torrents_files(torrent_hash=torrent_hash)
            file_paths = []
            
            for file_info in files:
                file_path = os.path.join(self.downloads_dir, torrent.name, file_info.name)
                if os.path.exists(file_path):
                    file_paths.append(file_path)
            
            return file_paths
            
        except Exception as e:
            logger.error(f"Ошибка получения файлов торрента: {e}")
            return []
    
    def remove_torrent(self, torrent_hash: str, delete_files: bool = False):
        """Удалить торрент из клиента"""
        try:
            if not self.is_connected():
                return
            
            self.client.torrents_delete(
                torrent_hashes=torrent_hash,
                delete_files=delete_files
            )
            
            logger.info(f"Торрент {torrent_hash} удалён")
            
        except Exception as e:
            logger.error(f"Ошибка удаления торрента: {e}")
    
    def pause_torrent(self, torrent_hash: str):
        """Поставить торрент на паузу"""
        try:
            if not self.is_connected():
                return
            
            self.client.torrents_pause(torrent_hashes=torrent_hash)
            logger.info(f"Торрент {torrent_hash} поставлен на паузу")
            
        except Exception as e:
            logger.error(f"Ошибка паузы торрента: {e}")
    
    def resume_torrent(self, torrent_hash: str):
        """Возобновить скачивание торрента"""
        try:
            if not self.is_connected():
                return
            
            self.client.torrents_resume(torrent_hashes=torrent_hash)
            logger.info(f"Торрент {torrent_hash} возобновлён")
            
        except Exception as e:
            logger.error(f"Ошибка возобновления торрента: {e}")