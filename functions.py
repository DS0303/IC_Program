# functions.py
import hashlib
import os
import psycopg2
from datetime import datetime
from typing import Optional
import threading

_stop_background = False  # Глобальный флаг для остановки фоновой проверки
_background_thread = None  # Глобальная переменная для хранения потока
_background_event = None  # Объект Event для управления ожиданием

def connect_to_db(dbname: str, user: str, password: str, host: str = "localhost", port: str = "5432") -> psycopg2.extensions.connection:
    """
    Устанавливает соединение с базой данных PostgreSQL.
    
    Args:
        dbname (str): Имя базы данных
        user (str): Имя пользователя
        password (str): Пароль
        host (str): Хост (по умолчанию "localhost")
        port (стр): Порт (по умолчанию "5432")
    
    Returns:
        psycopg2.extensions.connection: Объект соединения с базой данных
    
    Raises:
        psycopg2.Error: Если подключение не удалось
    """
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

def hash_file(file_path: str) -> Optional[str]:
    """Расчет хэша для файла."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        print(f"Ошибка при чтении файла {file_path}: {e}")
        return None

def hash_folder(folder_path: str) -> Optional[str]:
    """Расчет хэша для папки."""
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
        return sha256.hexdigest()
    except Exception as e:
        print(f"Ошибка при обработке папки {folder_path}: {e}")
        return None

def calculate_hash(resource_path: str) -> Optional[str]:
    """Выбор и расчет хэша для файла или папки."""
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

def get_resource_name(resource_path: str) -> str:
    """Извлечение имени файла или папки из пути."""
    try:
        cleaned_path = resource_path.rstrip(os.sep)
        return os.path.basename(cleaned_path)
    except Exception as e:
        print(f"Ошибка при извлечении имени из пути {resource_path}: {e}")
        return ""

def add_resource_to_db(conn, resource_path: str) -> bool:
    """
    Добавляет путь к файлу/папке и его имя в базу данных, если такого пути ещё нет.
    
    Args:
        conn: Соединение с базой данных psycopg2
        resource_path (str): Полный путь к файлу или папке
    
    Returns:
        bool: True если запись добавлена, False если ресурс уже существует или произошла ошибка
    """
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

def update_all_hashes(conn) -> None:
    """
    Рассчитывает хэш для всех ресурсов в базе данных и обновляет поля hash и hash_date.
    
    Args:
        conn: Соединение с базой данных psycopg2
    """
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

def check_all_hashes(conn) -> dict:
    """
    Проверяет целостность всех ресурсов в базе данных, сравнивая текущие хэши с сохранёнными.
    
    Args:
        conn: Соединение с базой данных psycopg2
    
    Returns:
        dict: Словарь с результатами проверки {resource_path: status}, где status может быть "passed", "failed", "unavailable", "no_hash"
    """
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

def remove_resource_from_db(conn, resource_path: str) -> bool:
    """
    Удаляет ресурс из базы данных по заданному пути.
    
    Args:
        conn: Соединение с базой данных psycopg2
        resource_path (str): Полный путь к ресурсу
    
    Returns:
        bool: True если удаление успешно, False если ресурс не найден или произошла ошибка
    """
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

def list_all_resources(conn) -> list:
    """
    Возвращает список всех ресурсов в базе данных.
    
    Args:
        conn: Соединение с базой данных psycopg2
    
    Returns:
        list: Список кортежей с данными ресурсов (resource_path, resource_name, resource_type, added_date, hash, hash_date)
    """
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

def start_background_check(conn, interval: int) -> None:
    """
    Запускает фоновую проверку целостности всех ресурсов с заданным интервалом.
    
    Args:
        conn: Соединение с базой данных psycopg2
        interval (int): Интервал проверки в секундах
    """
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
            check_all_hashes(conn)
            _background_event.wait(interval)
            if _stop_background:
                break

    if interval <= 0:
        print("Интервал должен быть положительным числом")
        return

    _background_thread = threading.Thread(target=periodic_check, daemon=True)
    _background_thread.start()
    print(f"Фоновая проверка запущена с интервалом {interval} секунд")

def stop_background_check() -> None:
    """Останавливает фоновую проверку."""
    global _stop_background
    global _background_thread
    global _background_event

    _stop_background = True
    if _background_event:
        _background_event.set()  # Прерываем ожидание
    if _background_thread:
        _background_thread.join()  # Ждём завершения потока
        _background_thread = None  # Сбрасываем поток
        _background_event = None   # Сбрасываем Event
    print("Фоновая проверка остановлена")