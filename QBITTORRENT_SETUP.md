# 🔧 Настройка qBittorrent для TorrentBot

## 📥 Установка qBittorrent

### Windows:
1. Скачайте qBittorrent с официального сайта: https://www.qbittorrent.org/download.php
2. Установите программу
3. Запустите qBittorrent

### Linux (Ubuntu/Debian):
```bash
sudo apt update
sudo apt install qbittorrent-nox
```

### Linux (CentOS/RHEL):
```bash
sudo yum install qbittorrent-nox
```

## ⚙️ Настройка Web UI

### Для обычной версии qBittorrent:
1. Запустите qBittorrent
2. Перейдите в **Инструменты** → **Настройки** (или **Tools** → **Options**)
3. В левом меню выберите **Web UI**
4. Поставьте галочку **"Enable the Web User Interface (Remote control)"**
5. Настройте параметры:
   - **IP адрес**: `*` (для всех интерфейсов) или `127.0.0.1` (только локально)
   - **Порт**: `8080` (или любой другой свободный порт)
   - **Имя пользователя**: `admin`
   - **Пароль**: создайте надежный пароль
6. Нажмите **OK**
7. Перезапустите qBittorrent

### Для qBittorrent-nox (headless версия):
1. Запустите qBittorrent-nox:
   ```bash
   qbittorrent-nox
   ```
2. При первом запуске он покажет временный пароль
3. Откройте браузер и перейдите на `http://localhost:8080`
4. Войдите с логином `admin` и временным паролем
5. Смените пароль в настройках

## 🔍 Проверка настройки

1. Откройте браузер
2. Перейдите на `http://localhost:8080` (или ваш IP:порт)
3. Введите логин и пароль
4. Если видите интерфейс qBittorrent - настройка выполнена правильно

## 🛠️ Настройка TorrentBot

В файле `config.py` укажите правильные параметры:

```python
# Настройки торрент-клиента (qBittorrent)
QBITTORRENT_HOST = "localhost"        # или IP адрес сервера
QBITTORRENT_PORT = 8080               # порт Web UI
QBITTORRENT_USERNAME = "admin"        # ваш логин
QBITTORRENT_PASSWORD = "ваш_пароль"   # ваш пароль
```

## 🔥 Firewall (если используете удаленный сервер)

Если qBittorrent установлен на удаленном сервере, откройте порт в firewall:

### Ubuntu/Debian:
```bash
sudo ufw allow 8080
```

### CentOS/RHEL:
```bash
sudo firewall-cmd --permanent --add-port=8080/tcp
sudo firewall-cmd --reload
```

## ❗ Важные замечания

1. **Безопасность**: Не открывайте Web UI в интернет без надежного пароля
2. **Порты**: Убедитесь, что выбранный порт не занят другими приложениями
3. **Права доступа**: qBittorrent должен иметь права на запись в папку загрузок
4. **Автозапуск**: Настройте автозапуск qBittorrent с системой

## 🚨 Устранение неполадок

### "Connection refused" или подобные ошибки:
1. Убедитесь, что qBittorrent запущен
2. Проверьте, что Web UI включен
3. Проверьте правильность хоста и порта в config.py
4. Убедитесь, что порт не заблокирован firewall

### "Login failed":
1. Проверьте правильность логина и пароля в config.py
2. Попробуйте войти через браузер с теми же данными

### Доступ только локально:
1. В настройках Web UI измените IP с `127.0.0.1` на `*`
2. Перезапустите qBittorrent

## 🔄 Автозапуск

### Windows (автозагрузка):
Добавьте qBittorrent в автозагрузку через меню "Пуск" → "Выполнить" → `shell:startup`

### Linux (systemd service):
Создайте файл `/etc/systemd/system/qbittorrent.service`:

```ini
[Unit]
Description=qBittorrent Daemon
After=network.target

[Service]
Type=forking
ExecStart=/usr/bin/qbittorrent-nox --daemon
User=qbittorrent
Group=qbittorrent

[Install]
WantedBy=multi-user.target
```

Затем:
```bash
sudo systemctl enable qbittorrent
sudo systemctl start qbittorrent
```

---

После настройки qBittorrent можно запускать TorrentBot!