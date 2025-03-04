import hashlib
import os
import psycopg2
from datetime import datetime
from typing import Optional, Callable
import threading

_stop_background = False  # Глобальный флаг для остановки фоновой проверки
_background_thread = None  # Глобальная переменная для хранения потока
_background_event = None  # Объект Event для управления ожиданием

# Подключение к базе данных
def connect_to_db(dbname: str, user: str, password: str, host: str = "localhost", port: str = "5432") -> psycopg2.extensions.connection:
    try:
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        print(f"Успешно подключено к базе данных {dbname}")
        return conn
    except psycopg2.Error as e:
        print(f"Ошибка подключения к БД: {e}")
        raise

# Расчет хэша для файла
def hash_file(file_path: str) -> Optional[str]:
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except PermissionError as e:
        print(f"Ошибка доступа к файлу {file_path}: отсутствуют права доступа ({e})")
        return None
    except OSError as e:
        print(f"Ошибка при чтении файла {file_path}: файл используется другим процессом или недоступен ({e})")
        return None
    except Exception as e:
        print(f"Ошибка при чтении файла {file_path}: {e}")
        return None

# Расчет хэша для папки
def hash_folder(folder_path: str) -> Optional[str]:
    sha256 = hashlib.sha256()
    try:
        for root, _, files in sorted(os.walk(folder_path)):
            for filename in sorted(files):
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, folder_path).encode('utf-8')
                sha256.update(rel_path)
                file_hash = hash_file(file_path)
                if file_hash:
                    sha256.update(file_hash.encode('utf-8'))
                else:
                    print(f"Пропущен файл {file_path} из-за ошибки доступа, продолжаем расчёт хэша для остальных файлов")
        return sha256.hexdigest()
    except PermissionError as e:
        print(f"Ошибка доступа к папке {folder_path}: отсутствуют права доступа ({e})")
        return None
    except Exception as e:
        print(f"Ошибка при обработке папки {folder_path}: {e}")
        return None

# Расчет хэша для ресурса
def calculate_hash(resource_path: str) -> Optional[str]:
    if not os.path.exists(resource_path):
        print(f"Файл/папка не существует: {resource_path}")
        return None
    if os.path.isfile(resource_path):
        return hash_file(resource_path)
    elif os.path.isdir(resource_path):
        return hash_folder(resource_path)
    else:
        print(f"Неподдерживаемый тип: {resource_path}")
        return None

# Извлечение имени ресурса из пути
def get_resource_name(resource_path: str) -> str:
    try:
        cleaned_path = resource_path.rstrip(os.sep)
        return os.path.basename(cleaned_path)
    except Exception as e:
        print(f"Ошибка при извлечении имени из пути {resource_path}: {e}")
        return ""

# Добавление ресурса в базу данных
def add_resource_to_db(conn, resource_path: str) -> bool:
    resource_name = get_resource_name(resource_path)
    resource_type = "file" if os.path.isfile(resource_path) else "folder" if os.path.isdir(resource_path) else None
    current_time = datetime.now()

    if not resource_name or not resource_type or not os.path.exists(resource_path):
        print(f"Не удалось добавить ресурс {resource_path}: некорректные данные или ресурс не существует")
        return False

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM resource_monitoring WHERE resource_path = %s", (resource_path,))
            count = cur.fetchone()[0]

            if count > 0:
                print(f"Ресурс {resource_path} уже существует в базе данных")
                return False

            cur.execute("""
                INSERT INTO resource_monitoring (resource_path, resource_name, resource_type, added_date)
                VALUES (%s, %s, %s, %s)
            """, (resource_path, resource_name, resource_type, current_time))
            conn.commit()
            print(f"Ресурс {resource_path} успешно добавлен в БД")
            return True
    except psycopg2.Error as e:
        print(f"Ошибка при записи в БД для {resource_path}: {e}")
        conn.rollback()
        return False

# Обновление хэшей для всех ресурсов
def update_all_hashes(conn) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT resource_path FROM resource_monitoring")
            resources = cur.fetchall()

            if not resources:
                print("В базе данных нет ресурсов для расчета хэшей")
                return

            updated_count = 0
            for (resource_path,) in resources:
                hash_value = calculate_hash(resource_path)
                if hash_value:
                    current_time = datetime.now()
                    cur.execute("""
                        UPDATE resource_monitoring
                        SET hash = %s, hash_date = %s
                        WHERE resource_path = %s
                    """, (hash_value, current_time, resource_path))
                    updated_count += 1
                else:
                    print(f"Не удалось рассчитать хэш для {resource_path}, пропускаем")

            conn.commit()
            print(f"Хэши успешно рассчитаны и обновлены для {updated_count} ресурсов")
    except psycopg2.Error as e:
        print(f"Ошибка при обновлении хэшей в БД: {e}")
        conn.rollback()

# Проверка хэшей для всех ресурсов
def check_all_hashes(conn) -> dict:
    results = {}  # Словарь для хранения результатов проверки
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT resource_path, hash FROM resource_monitoring")
            resources = cur.fetchall()

            if not resources:
                print("В базе данных нет ресурсов для проверки")
                return results

            for resource_path, stored_hash in resources:
                current_hash = calculate_hash(resource_path)
                if current_hash is None:
                    print(f"Ресурс {resource_path}: невозможно проверить (ресурс недоступен)")
                    results[resource_path] = "unavailable"
                elif stored_hash is None:
                    print(f"Ресурс {resource_path}: хэш в БД отсутствует")
                    results[resource_path] = "no_hash"
                elif current_hash == stored_hash:
                    print(f"Ресурс {resource_path}: целостность подтверждена")
                    results[resource_path] = "passed"
                else:
                    print(f"Ресурс {resource_path}: целостность нарушена (хэш изменился)")
                    results[resource_path] = "failed"

            conn.commit()
            return results
    except psycopg2.Error as e:
        print(f"Ошибка при проверке хэшей в БД: {e}")
        conn.rollback()
        return results

# Удаление ресурса из базы данных
def remove_resource_from_db(conn, resource_path: str) -> bool:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM resource_monitoring WHERE resource_path = %s", (resource_path,))
            count = cur.fetchone()[0]
            
            if count == 0:
                print(f"Ресурс {resource_path} не найден в базе данных")
                return False
            
            cur.execute("DELETE FROM resource_monitoring WHERE resource_path = %s", (resource_path,))
            conn.commit()
            print(f"Ресурс {resource_path} успешно удалён из БД")
            return True
    except psycopg2.Error as e:
        print(f"Ошибка при удалении ресурса {resource_path}: {e}")
        conn.rollback()
        return False

# Получение списка всех ресурсов
def list_all_resources(conn) -> list:
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT resource_path, resource_name, resource_type, added_date, hash, hash_date 
                FROM resource_monitoring
                ORDER BY added_date
            """)
            resources = cur.fetchall()
            return resources
    except psycopg2.Error as e:
        print(f"Ошибка при получении списка ресурсов: {e}")
        conn.rollback()
        return []

# Запуск фоновой проверки с callback для уведомлений о нарушениях и обновления таблицы
def start_background_check(conn, interval: int, alert_callback: Callable[[int, list], None] = None, refresh_callback: Callable[[], None] = None) -> None:
    global _stop_background
    global _background_thread
    global _background_event

    # Сбрасываем флаг остановки
    _stop_background = False

    # Проверяем, не запущен ли уже поток
    if _background_thread and _background_thread.is_alive():
        print("Фоновая проверка уже запущена")
        return

    # Создаём новый объект Event для контроля ожидания
    _background_event = threading.Event()

    def periodic_check():
        while not _stop_background:
            print(f"Начало фоновой проверки в {datetime.now()}")
            # Выполняем проверку и получаем результаты
            results = check_all_hashes(conn)
            # Подсчитываем количество нарушений (статус "failed") и собираем пути
            failed_paths = [path for path, status in results.items() if status == "failed"]
            failed_count = len(failed_paths)
            # Если есть нарушения и задан callback, вызываем его
            if failed_count > 0 and alert_callback:
                alert_callback(failed_count, failed_paths)
                break  # Прерываем цикл, чтобы остановить фоновую проверку
            # Обновляем таблицу через callback
            if refresh_callback:
                # Вызываем обновление таблицы в главном потоке
                refresh_callback()
            _background_event.wait(interval)

    if interval <= 0:
        print("Интервал должен быть положительным числом")
        return

    _background_thread = threading.Thread(target=periodic_check, daemon=True)
    _background_thread.start()
    print(f"Фоновая проверка запущена с интервалом {interval} секунд")

# Остановка фоновой проверки
def stop_background_check() -> None:
    global _stop_background
    global _background_thread
    global _background_event

    _stop_background = True
    if _background_event:
        _background_event.set()  # Прерываем ожидание
    # Удаляем вызов join(), чтобы избежать deadlock
    _background_thread = None
    _background_event = None
    print("Фоновая проверка остановлена")