"""
Утилиты для администрирования бота
"""
import sys
import os

# Добавляем путь к модулям
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.torrent_logger import torrent_logger
from src.cleanup_manager import CleanupManager
import json


def show_stats(days=7):
    """Показать статистику операций"""
    stats = torrent_logger.get_operation_stats(days)
    
    print(f"📊 Статистика за последние {days} дней:")
    print(f"Всего операций: {stats.get('total_operations', 0)}")
    
    print("\n📈 По типам операций:")
    for op_type, count in stats.get('operations_by_type', {}).items():
        print(f"  {op_type}: {count}")
    
    print("\n📋 По статусам:")
    for status, count in stats.get('operations_by_status', {}).items():
        print(f"  {status}: {count}")
    
    print("\n👥 Активные пользователи:")
    for user in stats.get('active_users', []):
        print(f"  {user['user_name']} (ID: {user['user_id']}): {user['count']} операций")
    
    total_size = stats.get('total_transferred_bytes', 0)
    if total_size > 0:
        size_gb = total_size / (1024**3)
        print(f"\n💾 Передано данных: {size_gb:.2f} ГБ")


def cleanup_logs(days=30):
    """Очистить старые логи"""
    print(f"🗑️ Очистка логов старше {days} дней...")
    torrent_logger.cleanup_old_logs(days)
    print("✅ Очистка завершена")


def force_cleanup():
    """Принудительная очистка временных файлов"""
    print("🗑️ Запуск принудительной очистки...")
    cleanup_manager = CleanupManager()
    cleanup_manager.force_cleanup()
    print("✅ Принудительная очистка завершена")


def disk_usage():
    """Показать использование диска"""
    cleanup_manager = CleanupManager()
    stats = cleanup_manager.get_disk_usage_stats()
    
    print("💾 Использование дискового пространства:")
    print(f"Временные файлы: {cleanup_manager.format_size(stats.get('temp_size', 0))}")
    print(f"Загрузки: {cleanup_manager.format_size(stats.get('downloads_size', 0))}")
    print(f"Всего используется: {cleanup_manager.format_size(stats.get('total_size', 0))}")
    print(f"Лимит: {cleanup_manager.format_size(stats.get('max_size', 0))}")
    print(f"Использовано: {stats.get('usage_percent', 0):.1f}%")
    print(f"Свободно: {cleanup_manager.format_size(stats.get('free_space', 0))}")


def export_logs(output_file="logs_export.json", days=30):
    """Экспортировать логи в JSON"""
    print(f"📤 Экспорт логов за {days} дней в {output_file}...")
    success = torrent_logger.export_logs_to_json(output_file, days)
    if success:
        print("✅ Экспорт завершён успешно")
    else:
        print("❌ Ошибка экспорта")


def main():
    """Главная функция утилиты"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Утилиты администрирования TorrentBot")
    parser.add_argument("command", choices=[
        "stats", "cleanup-logs", "force-cleanup", "disk-usage", "export-logs"
    ], help="Команда для выполнения")
    parser.add_argument("--days", type=int, default=7, 
                       help="Количество дней для статистики/очистки")
    parser.add_argument("--output", default="logs_export.json",
                       help="Файл для экспорта логов")
    
    args = parser.parse_args()
    
    if args.command == "stats":
        show_stats(args.days)
    elif args.command == "cleanup-logs":
        cleanup_logs(args.days)
    elif args.command == "force-cleanup":
        force_cleanup()
    elif args.command == "disk-usage":
        disk_usage()
    elif args.command == "export-logs":
        export_logs(args.output, args.days)


if __name__ == "__main__":
    main()