"""
Модуль для работы с торрент-клиентом qBittorrent
"""
import os
import time
import logging
from typing import Optional, Dict, Any, List, Union
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
        self.client: Optional[qbittorrentapi.Client] = None
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
            
            logger.info(f"Добавление торрент-файла: {filename} (размер: {len(torrent_data)} байт)")
            
            # Получаем список торрентов до добавления
            existing_torrents = set()
            try:
                if self.client:
                    existing_list = self.client.torrents_info()
                    existing_torrents = {t.hash for t in existing_list}
                    logger.info(f"Существующих торрентов: {len(existing_torrents)}")
            except Exception as e:
                logger.warning(f"Не удалось получить список существующих торрентов: {e}")
            
            # Сохраняем торрент во временный файл
            with tempfile.NamedTemporaryFile(suffix='.torrent', delete=False) as temp_file:
                temp_file.write(torrent_data)
                temp_file_path = temp_file.name
            
            try:
                # Добавляем торрент
                logger.info(f"Отправка торрента в qBittorrent...")
                if not self.client:
                    raise Exception("Клиент qBittorrent не подключен")
                    
                result = self.client.torrents_add(
                    torrent_files=temp_file_path,
                    save_path=self.downloads_dir
                )
                
                logger.info(f"Результат добавления: {result}")
                
                # Получаем hash добавленного торрента
                if result == "Ok.":
                    # Ждём, чтобы торрент появился в списке
                    for attempt in range(10):  # Пытаемся 10 раз
                        time.sleep(0.5)  # Ждём 500мс между попытками
                        
                        try:
                            if not self.client:
                                break
                            current_torrents = self.client.torrents_info()
                            current_hashes = {t.hash for t in current_torrents}
                            
                            # Ищем новые торренты
                            new_torrents = current_hashes - existing_torrents
                            
                            if new_torrents:
                                new_hash = list(new_torrents)[0]
                                # Получаем информацию о новом торренте
                                for torrent in current_torrents:
                                    if torrent.hash == new_hash:
                                        logger.info(f"Торрент успешно добавлен: {torrent.name} ({torrent.hash})")
                                        return torrent.hash
                            
                            logger.info(f"Попытка {attempt + 1}/10: торрент ещё не появился в списке")
                            
                        except Exception as e:
                            logger.warning(f"Ошибка при проверке торрентов (попытка {attempt + 1}): {e}")
                    
                    # Если новых торрентов не найдено, пытаемся найти по имени
                    logger.warning("Не удалось найти новый торрент, ищем по имени файла...")
                    try:
                        if not self.client:
                            return None
                        all_torrents = self.client.torrents_info()
                        base_filename = os.path.splitext(filename)[0]  # Убираем расширение .torrent
                        
                        for torrent in all_torrents:
                            # Проверяем различные варианты совпадения имён
                            if (base_filename.lower() in torrent.name.lower() or 
                                torrent.name.lower() in base_filename.lower() or
                                filename.lower() in torrent.name.lower()):
                                logger.info(f"Найден торрент по имени: {torrent.name} ({torrent.hash})")
                                return torrent.hash
                        
                        # Последняя попытка - берём самый последний добавленный
                        if all_torrents:
                            latest_torrent = max(all_torrents, key=lambda t: t.added_on)
                            logger.info(f"Взят последний добавленный торрент: {latest_torrent.name} ({latest_torrent.hash})")
                            return latest_torrent.hash
                            
                    except Exception as e:
                        logger.error(f"Ошибка поиска торрента по имени: {e}")
                else:
                    logger.error(f"qBittorrent вернул ошибку: {result}")
                
                return None
                
            finally:
                # Удаляем временный файл
                try:
                    os.unlink(temp_file_path)
                except Exception as e:
                    logger.warning(f"Не удалось удалить временный файл: {e}")
                    
        except Exception as e:
            logger.error(f"Ошибка добавления торрент-файла: {e}", exc_info=True)
            return None
    
    def add_magnet_link(self, magnet_link: str) -> Optional[str]:
        """
        Добавить торрент по magnet-ссылке
        Возвращает hash торрента или None при ошибке
        """
        try:
            if not self.is_connected():
                self._connect()
                
            if not self.is_connected() or not self.client:
                raise Exception("Не удалось подключиться к qBittorrent")
            
            logger.info(f"Добавление magnet-ссылки...")
            
            # Получаем список торрентов до добавления
            existing_torrents = set()
            try:
                existing_list = self.client.torrents_info()
                existing_torrents = {t.hash for t in existing_list}
                logger.info(f"Существующих торрентов: {len(existing_torrents)}")
            except Exception as e:
                logger.warning(f"Не удалось получить список существующих торрентов: {e}")
            
            # Добавляем магнет-ссылку
            result = self.client.torrents_add(
                urls=magnet_link,
                save_path=self.downloads_dir
            )
            
            logger.info(f"Результат добавления magnet: {result}")
            
            if result == "Ok.":
                # Ждём, чтобы торрент появился в списке
                for attempt in range(15):  # Для magnet-ссылок может понадобиться больше времени
                    time.sleep(1)  # Ждём 1 секунду между попытками
                    
                    try:
                        current_torrents = self.client.torrents_info()
                        current_hashes = {t.hash for t in current_torrents}
                        
                        # Ищем новые торренты
                        new_torrents = current_hashes - existing_torrents
                        
                        if new_torrents:
                            new_hash = list(new_torrents)[0]
                            # Получаем информацию о новом торренте
                            for torrent in current_torrents:
                                if torrent.hash == new_hash:
                                    logger.info(f"Magnet-ссылка успешно добавлена: {torrent.name} ({torrent.hash})")
                                    return torrent.hash
                        
                        logger.info(f"Попытка {attempt + 1}/15: торрент ещё не появился в списке")
                        
                    except Exception as e:
                        logger.warning(f"Ошибка при проверке торрентов (попытка {attempt + 1}): {e}")
                
                # Последняя попытка - берём самый последний добавленный
                try:
                    all_torrents = self.client.torrents_info()
                    if all_torrents:
                        latest_torrent = max(all_torrents, key=lambda t: t.added_on)
                        logger.info(f"Взят последний добавленный торрент: {latest_torrent.name} ({latest_torrent.hash})")
                        return latest_torrent.hash
                except Exception as e:
                    logger.error(f"Ошибка получения последнего торрента: {e}")
            else:
                logger.error(f"qBittorrent вернул ошибку: {result}")
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка добавления magnet-ссылки: {e}", exc_info=True)
            return None
    
    def get_torrent_info(self, torrent_hash: str) -> Optional[Dict[str, Any]]:
        """Получить информацию о торренте"""
        try:
            if not self.is_connected() or not self.client:
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
            if not self.is_connected() or not self.client:
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
            if not self.is_connected() or not self.client:
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
            if not self.is_connected() or not self.client:
                return
            
            self.client.torrents_pause(torrent_hashes=torrent_hash)
            logger.info(f"Торрент {torrent_hash} поставлен на паузу")
            
        except Exception as e:
            logger.error(f"Ошибка паузы торрента: {e}")
    
    def resume_torrent(self, torrent_hash: str):
        """Возобновить скачивание торрента"""
        try:
            if not self.is_connected() or not self.client:
                return
            
            self.client.torrents_resume(torrent_hashes=torrent_hash)
            logger.info(f"Торрент {torrent_hash} возобновлён")
            
        except Exception as e:
            logger.error(f"Ошибка возобновления торрента: {e}")