# Решение проблемы с Python 3.13

## Проблема
При использовании Python 3.13 возникает ошибка:
```
AttributeError: 'Updater' object has no attribute '_Updater__polling_cleanup_cb' and no __dict__ for setting new attributes
```

## Причина
Python 3.13 внёс изменения в работу с атрибутами классов и `__slots__`, что несовместимо с текущими версиями python-telegram-bot.

## Решение
Используйте Python 3.12 вместо Python 3.13.

## Инструкции по запуску

### Вариант 1: Использование созданного окружения Python 3.12
```powershell
# Активация окружения
.\.venv_py312\Scripts\Activate.ps1

# Запуск бота
python main.py
```

### Вариант 2: Создание нового окружения
```powershell
# Создание нового виртуального окружения с Python 3.12
python -m venv .venv_py312

# Активация окружения
.\.venv_py312\Scripts\Activate.ps1

# Установка зависимостей
pip install -r requirements.txt

# Запуск бота
python main.py
```

### Быстрый запуск без активации окружения
```powershell
.\.venv_py312\Scripts\python.exe main.py
```

## Проверка версии Python
```powershell
python --version
```
Должна быть Python 3.12.x

## Статус решения
✅ Проблема решена
✅ Бот успешно запускается с Python 3.12
✅ Все функции работают корректно