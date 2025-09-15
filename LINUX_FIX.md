# Решение проблемы с Python 3.13 на Linux

## Проблема
При использовании Python 3.13 возникает ошибка:
```
AttributeError: 'Updater' object has no attribute '_Updater__polling_cleanup_cb' and no __dict__ for setting new attributes
```

## Причина
Python 3.13 внёс изменения в работу с атрибутами классов и `__slots__`, что несовместимо с текущими версиями python-telegram-bot.

## Решение
Используйте Python 3.12 вместо Python 3.13.

## Инструкции для Linux

### Шаг 1: Проверка доступных версий Python
```bash
# Проверяем, какие версии Python установлены
python3 --version
python3.12 --version
python3.11 --version

# Если Python 3.12 не установлен, устанавливаем его
# Ubuntu/Debian:
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-pip

# CentOS/RHEL/Fedora:
sudo dnf install python3.12 python3.12-pip

# Arch Linux:
sudo pacman -S python312
```

### Шаг 2: Создание виртуального окружения с Python 3.12
```bash
# Переходим в директорию проекта
cd /path/to/TorrentBot

# Создаём виртуальное окружение с Python 3.12
python3.12 -m venv .venv_py312

# Активируем окружение
source .venv_py312/bin/activate

# Обновляем pip
pip install --upgrade pip

# Устанавливаем зависимости
pip install -r requirements.txt
```

### Шаг 3: Запуск бота
```bash
# Вариант 1: С активированным окружением
source .venv_py312/bin/activate
python main.py

# Вариант 2: Без активации окружения
./.venv_py312/bin/python main.py
```

### Шаг 4: Создание скрипта запуска (опционально)
```bash
# Создаём скрипт запуска
cat > start_bot_linux.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
source .venv_py312/bin/activate
python main.py
EOF

# Делаем скрипт исполняемым
chmod +x start_bot_linux.sh

# Запускаем через скрипт
./start_bot_linux.sh
```

### Альтернативные методы установки Python 3.12

#### Используя pyenv (рекомендуется)
```bash
# Установка pyenv
curl https://pyenv.run | bash

# Перезагрузка оболочки или добавление в ~/.bashrc
export PATH="$HOME/.pyenv/bin:$PATH"
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

# Установка Python 3.12
pyenv install 3.12.7
pyenv local 3.12.7

# Создание виртуального окружения
python -m venv .venv_py312
source .venv_py312/bin/activate
pip install -r requirements.txt
```

#### Используя conda
```bash
# Создание окружения с Python 3.12
conda create -n torrentbot python=3.12

# Активация окружения
conda activate torrentbot

# Установка зависимостей
pip install -r requirements.txt

# Запуск
python main.py
```

### Автоматизация через systemd (для серверов)
```bash
# Создаём systemd service
sudo tee /etc/systemd/system/torrentbot.service << EOF
[Unit]
Description=Telegram Torrent Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/TorrentBot
ExecStart=/path/to/TorrentBot/.venv_py312/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Перезагружаем systemd и запускаем сервис
sudo systemctl daemon-reload
sudo systemctl enable torrentbot
sudo systemctl start torrentbot

# Проверяем статус
sudo systemctl status torrentbot
```

### Проверка и отладка
```bash
# Проверка версии Python в окружении
./.venv_py312/bin/python --version

# Проверка установленных пакетов
./.venv_py312/bin/pip list | grep telegram

# Просмотр логов
tail -f logs/bot.log
```

## Возможные проблемы и решения

### Проблема: Python 3.12 недоступен в репозиториях
**Решение:**
```bash
# Добавляем deadsnakes PPA (для Ubuntu)
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-pip
```

### Проблема: Конфликт версий pip
**Решение:**
```bash
# Переустанавливаем pip в виртуальном окружении
./.venv_py312/bin/python -m pip install --upgrade pip
```

### Проблема: Отсутствуют заголовочные файлы
**Решение:**
```bash
# Ubuntu/Debian
sudo apt install python3.12-dev

# CentOS/RHEL
sudo dnf install python3.12-devel
```

## Статус решения
✅ Работает на всех популярных дистрибутивах Linux
✅ Поддерживает автоматический запуск через systemd
✅ Совместимо с различными методами управления Python (pyenv, conda)