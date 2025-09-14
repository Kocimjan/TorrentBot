"""
Скрипт для первичной настройки администратора
Запустите этот скрипт перед первым запуском бота
"""
import sys
import os

# Добавляем путь к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.user_manager import user_manager


def setup_first_admin():
    """Настройка первого администратора"""
    print("🛠️ Настройка первого администратора")
    print()
    
    # Получаем ID пользователя
    while True:
        try:
            user_id = int(input("Введите ваш Telegram ID: "))
            break
        except ValueError:
            print("❌ Неверный формат. Введите числовой ID.")
    
    # Получаем имя пользователя (опционально)
    username = input("Введите ваш username (необязательно): ").strip()
    if not username:
        username = None
    
    first_name = input("Введите ваше имя (необязательно): ").strip()
    if not first_name:
        first_name = "Admin"
    
    # Проверяем, существует ли пользователь
    if user_manager.user_exists(user_id):
        print(f"⚠️ Пользователь {user_id} уже существует в системе.")
        
        if user_manager.is_admin(user_id):
            print("✅ Пользователь уже является администратором.")
            return
        else:
            # Повышаем до админа
            success = user_manager.promote_to_admin(user_id, promoted_by=user_id)
            if success:
                print("✅ Пользователь повышен до администратора.")
            else:
                print("❌ Ошибка при повышении пользователя.")
    else:
        # Добавляем нового админа
        success = user_manager.add_user(
            user_id=user_id,
            username=username,
            first_name=first_name,
            role="admin",
            added_by=user_id
        )
        
        if success:
            print("✅ Администратор успешно добавлен!")
            print(f"ID: {user_id}")
            print(f"Имя: {first_name}")
            if username:
                print(f"Username: @{username}")
        else:
            print("❌ Ошибка при добавлении администратора.")
    
    print()
    print("🚀 Теперь можете запускать бота командой: python main.py")


if __name__ == "__main__":
    try:
        # Создаем директории если их нет
        from config import LOGS_DIR
        os.makedirs(LOGS_DIR, exist_ok=True)
        
        setup_first_admin()
    except KeyboardInterrupt:
        print("\n❌ Настройка отменена.")
    except Exception as e:
        print(f"❌ Ошибка: {e}")