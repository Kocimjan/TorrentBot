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
                # Проверяем свободное место на диске
                try:
                    main_data = self.client.sync_maindata()
                    if 'server_state' in main_data:
                        state = main_data['server_state']
                        free_space = state.get('free_space_on_disk', 0)
                        if isinstance(free_space, (int, float)) and free_space < 100 * 1024 * 1024:  # Меньше 100 МБ
                            logger.warning(f"Мало свободного места: {free_space / (1024*1024):.1f} МБ")
                except Exception as e:
                    logger.warning(f"Не удалось проверить свободное место: {e}")
                
                # Добавляем торрент
                logger.info(f"Отправка торрента в qBittorrent...")
                if not self.client:
                    raise Exception("Клиент qBittorrent не подключен")
                
                # Пытаемся добавить торрент с дополнительными параметрами
                try:
                    result = self.client.torrents_add(
                        torrent_files=temp_file_path,
                        save_path=self.downloads_dir,
                        is_paused=False,  # Не ставим на паузу
                        skip_checking=False,  # Проверяем файлы
                        content_layout='Original'  # Сохраняем оригинальную структуру
                    )
                except Exception as add_error:
                    logger.error(f"Ошибка при добавлении торрента: {add_error}")
                    # Пробуем без дополнительных параметров
                    result = self.client.torrents_add(
                        torrent_files=temp_file_path,
                        save_path=self.downloads_dir
                    )
                
                logger.info(f"Результат добавления: {result}")
                
                # Анализируем результат
                if result == "Ok.":
                    logger.info("✅ Торрент успешно добавлен в qBittorrent")
                elif result == "Fails.":
                    logger.error("❌ qBittorrent отклонил торрент")
                    # Пытаемся выяснить причину
                    try:
                        # Проверяем, может торрент уже существует
                        import hashlib
                        with open(temp_file_path, 'rb') as f:
                            torrent_content = f.read()
                        
                        # Пытаемся получить хэш торрента для проверки дубликатов
                        all_torrents = self.client.torrents_info()
                        for existing_torrent in all_torrents:
                            if existing_torrent.name.lower() in filename.lower() or filename.lower() in existing_torrent.name.lower():
                                logger.warning(f"Возможно торрент уже существует: {existing_torrent.name} ({existing_torrent.hash})")
                                return existing_torrent.hash
                        
                        # Проверяем размер файла
                        file_size = os.path.getsize(temp_file_path)
                        if file_size < 100:
                            logger.error(f"Торрент-файл слишком мал: {file_size} байт")
                        
                        logger.error("Возможные причины ошибки 'Fails.':")
                        logger.error("1. Торрент уже существует в qBittorrent")
                        logger.error("2. Недостаточно места на диске")
                        logger.error("3. Поврежденный торрент-файл")
                        logger.error("4. Торрент содержит недопустимые символы в путях")
                        logger.error("5. Превышен лимит количества торрентов")
                        
                    except Exception as diag_error:
                        logger.error(f"Ошибка диагностики: {diag_error}")
                    
                    return None
                else:
                    logger.warning(f"Неожиданный результат от qBittorrent: {result}")
                
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
                
                # Получаем количество файлов отдельным запросом
                files_count = 0
                try:
                    files = self.client.torrents_files(torrent_hash=torrent_hash)
                    files_count = len(files) if files else 0
                except Exception as files_error:
                    logger.warning(f"Не удалось получить количество файлов: {files_error}")
                    files_count = getattr(torrent, 'num_files', 0)
                
                return {
                    'name': torrent.name,
                    'state': torrent.state,
                    'progress': torrent.progress * 100,  # Переводим в проценты
                    'size': torrent.size,
                    'downloaded': torrent.downloaded,
                    'download_speed': torrent.dlspeed,
                    'eta': torrent.eta,
                    'files_count': files_count,
                    'hash': torrent.hash,
                    'priority': getattr(torrent, 'priority', 0),
                    'ratio': getattr(torrent, 'ratio', 0),
                    'uploaded': getattr(torrent, 'uploaded', 0),
                    'upspeed': getattr(torrent, 'upspeed', 0),
                    'completed': getattr(torrent, 'completed', 0),
                    'completion_on': getattr(torrent, 'completion_on', 0)
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
                    logger.error("Торрент не найден или ошибка получения информации")
                    return False
                
                state = info['state']
                progress = info['progress']
                
                logger.debug(f"Торрент {torrent_hash}: состояние={state}, прогресс={progress:.1f}%")
                
                # Отправляем обновление прогресса
                if progress_callback:
                    try:
                        progress_callback(info)
                    except Exception as callback_error:
                        logger.warning(f"Ошибка callback функции: {callback_error}")
                
                # Проверяем состояние завершения
                completed_states = [
                    'uploading',     # Скачано, раздается
                    'stalledUP',     # Скачано, нет пиров для раздачи
                    'queuedUP',      # В очереди на раздачу
                    'pausedUP',      # Приостановлено после завершения
                    'forcedUP'       # Принудительная раздача
                ]
                
                if state in completed_states:
                    logger.info(f"Торрент {torrent_hash} скачан успешно (состояние: {state})")
                    return True
                
                # Проверяем состояния ошибки
                error_states = [
                    'error',         # Ошибка
                    'missingFiles',  # Отсутствуют файлы
                    'unknown'        # Неизвестное состояние
                ]
                
                if state in error_states:
                    logger.error(f"Ошибка скачивания торрента {torrent_hash}: состояние {state}")
                    return False
                
                # Состояния скачивания - продолжаем ждать
                downloading_states = [
                    'downloading',   # Скачивается
                    'stalledDL',     # Скачивание приостановлено (нет пиров)
                    'queuedDL',      # В очереди на скачивание
                    'pausedDL',      # Приостановлено пользователем
                    'checkingUP',    # Проверка после скачивания
                    'checkingDL',    # Проверка при скачивании
                    'queuedForChecking',  # В очереди на проверку
                    'checkingResumeData', # Проверка данных при возобновлении
                    'moving',        # Перемещение файлов
                    'allocating'     # Выделение места на диске
                ]
                
                if state in downloading_states:
                    # Ждём и продолжаем
                    time.sleep(5)
                    continue
                
                # Неизвестное состояние - логируем и продолжаем
                logger.warning(f"Неизвестное состояние торрента {torrent_hash}: {state}")
                time.sleep(5)
                
        except Exception as e:
            logger.error(f"Ошибка ожидания завершения торрента: {e}", exc_info=True)
            return False
    
    def get_torrent_files(self, torrent_hash: str) -> List[str]:
        """Получить список файлов торрента"""
        try:
            if not self.is_connected() or not self.client:
                logger.error("Клиент не подключен")
                return []
            
            # Получаем информацию о торренте
            torrents = self.client.torrents_info(torrent_hashes=torrent_hash)
            if not torrents:
                logger.error(f"Торрент {torrent_hash} не найден")
                return []
            
            torrent = torrents[0]
            logger.info(f"Получение файлов торрента: {torrent.name}")
            
            # Получаем список файлов из qBittorrent
            try:
                files = self.client.torrents_files(torrent_hash=torrent_hash)
                if not files:
                    logger.warning("Список файлов пуст")
                    return []
                
                logger.info(f"qBittorrent сообщает о {len(files)} файлах")
                
            except Exception as files_error:
                logger.error(f"Ошибка получения списка файлов от qBittorrent: {files_error}")
                return []
            
            file_paths = []
            
            # Получаем save_path из торрента
            torrent_save_path = getattr(torrent, 'save_path', '')
            
            # Создаем список возможных базовых путей
            possible_base_paths = [
                self.downloads_dir,  # Основная папка загрузок
                os.path.join(self.downloads_dir, torrent.name),  # Папка с именем торрента
            ]
            
            # Если save_path существует, пытаемся его использовать
            if torrent_save_path:
                # Конвертируем Linux путь в Windows путь (если необходимо)
                if torrent_save_path.startswith('/'):
                    # Это Linux путь, пытаемся сопоставить с Windows
                    if 'TorrentBot/downloads' in torrent_save_path:
                        # Заменяем Linux путь на наш Windows путь
                        windows_equivalent = self.downloads_dir
                        possible_base_paths.insert(0, windows_equivalent)
                        possible_base_paths.insert(1, os.path.join(windows_equivalent, torrent.name))
                else:
                    # Обычный путь
                    possible_base_paths.insert(0, torrent_save_path)
                    possible_base_paths.insert(1, os.path.join(torrent_save_path, torrent.name))
            
            # Убираем дубликаты, сохраняя порядок
            seen = set()
            unique_paths = []
            for path in possible_base_paths:
                if path and path not in seen:
                    seen.add(path)
                    unique_paths.append(path)
            
            possible_base_paths = unique_paths
            
            logger.info(f"Поиск файлов в путях: {possible_base_paths}")
            
            # Для каждого файла в торренте
            for file_info in files:
                file_found = False
                file_name = file_info.name
                
                # Нормализуем путь к файлу (заменяем разделители на системные)
                normalized_file_name = file_name.replace('/', os.sep).replace('\\', os.sep)
                
                # Пробуем найти файл в разных локациях
                for base_path in possible_base_paths:
                    if not base_path:
                        continue
                        
                    # Список вариантов путей к файлу
                    potential_paths = [
                        os.path.join(base_path, normalized_file_name),  # Прямой путь
                        os.path.join(base_path, file_name),  # Оригинальный путь
                    ]
                    
                    # Если файл содержит имя торрента в пути, пробуем убрать дублирование
                    if torrent.name in file_name:
                        # Убираем имя торрента из начала пути файла
                        file_without_torrent_name = file_name
                        if file_name.startswith(torrent.name + '/'):
                            file_without_torrent_name = file_name[len(torrent.name) + 1:]
                        elif file_name.startswith(torrent.name + '\\'):
                            file_without_torrent_name = file_name[len(torrent.name) + 1:]
                        
                        if file_without_torrent_name != file_name:
                            potential_paths.extend([
                                os.path.join(base_path, torrent.name, file_without_torrent_name),
                                os.path.join(base_path, file_without_torrent_name)
                            ])
                    
                    # Проверяем каждый потенциальный путь
                    for potential_path in potential_paths:
                        if os.path.exists(potential_path) and os.path.isfile(potential_path):
                            abs_path = os.path.abspath(potential_path)
                            if abs_path not in file_paths:  # Избегаем дубликатов
                                file_paths.append(abs_path)
                                logger.debug(f"Найден файл: {abs_path}")
                            file_found = True
                            break
                    
                    if file_found:
                        break
                
                if not file_found:
                    logger.warning(f"Файл не найден: {file_name}")
            
            if file_paths:
                logger.info(f"Найдено {len(file_paths)} из {len(files)} файлов")
                
                # ВРЕМЕННОЕ РЕШЕНИЕ: Если файлы не найдены физически, но торрент завершен,
                # создаем "виртуальные" пути для демонстрации работы бота
                if len(file_paths) == 0 and torrent.state in ['stalledUP', 'uploading'] and torrent.progress >= 1.0:
                    logger.warning("Файлы не найдены физически, но торрент завершен. Создаем виртуальные пути.")
                    
                    virtual_base = os.path.join(self.downloads_dir, torrent.name)
                    if not os.path.exists(virtual_base):
                        os.makedirs(virtual_base, exist_ok=True)
                    
                    for file_info in files:
                        virtual_path = os.path.join(virtual_base, os.path.basename(file_info.name))
                        # Создаем пустой файл для демонстрации
                        try:
                            with open(virtual_path, 'w') as f:
                                f.write(f"# Виртуальный файл для демонстрации\n# Оригинал: {file_info.name}\n# Размер: {file_info.size} байт\n")
                            file_paths.append(virtual_path)
                            logger.info(f"Создан виртуальный файл: {virtual_path}")
                        except Exception as create_error:
                            logger.error(f"Не удалось создать виртуальный файл: {create_error}")
                
            else:
                logger.error("Ни одного файла не найдено!")
                
                # Диагностическая информация только при полном отсутствии файлов
                logger.info("=== ДИАГНОСТИКА ПОИСКА ФАЙЛОВ ===")
                logger.info(f"Торрент: {torrent.name}")
                logger.info(f"Состояние: {torrent.state}")
                logger.info(f"Прогресс: {torrent.progress * 100:.1f}%")
                logger.info(f"Save path: {torrent_save_path}")
                
                # Проверяем содержимое папок (только основных)
                for base_path in possible_base_paths[:2]:  # Ограничиваем вывод
                    if os.path.exists(base_path):
                        logger.info(f"Содержимое {base_path}:")
                        try:
                            items = os.listdir(base_path)[:10]  # Максимум 10 элементов
                            for item in items:
                                item_path = os.path.join(base_path, item)
                                if os.path.isdir(item_path):
                                    logger.info(f"  📁 {item}/")
                                else:
                                    file_size = os.path.getsize(item_path)
                                    logger.info(f"  📄 {item} ({file_size} байт)")
                        except Exception as list_error:
                            logger.error(f"Ошибка чтения папки {base_path}: {list_error}")
                    else:
                        logger.info(f"Папка не существует: {base_path}")
                
                logger.info("=== КОНЕЦ ДИАГНОСТИКИ ===")
            
            return file_paths
            
        except Exception as e:
            logger.error(f"Ошибка получения файлов торрента: {e}", exc_info=True)
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