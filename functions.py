import hashlib
import os
import psycopg2
import threading
from typing import Optional
from datetime import datetime

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

# Хэш файла
def hash_file(file_path: str) -> Optional[str]:
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        print(f"Ошибка при чтении файла {file_path}: {e}")
        return None

# Хэш папки
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
        return sha256.hexdigest()
    except Exception as e:
        print(f"Ошибка при обработке папки {folder_path}: {e}")
        return None

# Выбор и расчет хэша для ресурса
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

# Извлечение имени ресурса
def get_resource_name(resource_path: str) -> Optional[str]:
    try:
        return os.path.basename(resource_path)
    except Exception as e:
        print(f"Ошибка при извлечении имени из пути {resource_path}: {e}")
        return None

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
    
# Обновление хэшей для всех ресурсов в базе данных
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

# Проверка целостности всех ресурсов в базе данных
def check_all_hashes(conn) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT resource_path, hash FROM resource_monitoring")
            resources = cur.fetchall()
            if not resources:
                print("В базе данных нет ресурсов для проверки")
                return
            for resource_path, stored_hash in resources:
                current_hash = calculate_hash(resource_path)
                if current_hash is None:
                    print(f"Ресурс {resource_path}: невозможно проверить (ресурс недоступен)")
                elif stored_hash is None:
                    print(f"Ресурс {resource_path}: хэш в БД отсутствует")
                elif current_hash == stored_hash:
                    print(f"Ресурс {resource_path}: целостность подтверждена")
                else:
                    print(f"Ресурс {resource_path}: целостность нарушена")
            conn.commit()
    except psycopg2.Error as e:
        print(f"Ошибка при проверке хэшей в БД: {e}")
        conn.rollback()

# Вывод списка всех ресурсов в базе данных
def list_all_resources(conn) -> list:
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT resource_path, resource_name, resource_type, added_date, hash, hash_date 
                FROM resource_monitoring
                ORDER BY added_date
            """)
            resources = cur.fetchall()
            
            if not resources:
                print("В базе данных нет ресурсов")
            else:
                print("Список контролируемых ресурсов:")
                for res in resources:
                    path, name, rtype, added, _, hash_date = res
                    hash_date_str = hash_date if hash_date else "Нет данных"
                    print(f"Путь: {path}, Имя: {name}, Тип: {rtype}, Добавлен: {added}, Дата хэша: {hash_date_str}")
            return resources
    except psycopg2.Error as e:
        print(f"Ошибка при получении списка ресурсов: {e}")
        conn.rollback()
        return []
    
# Запуск фоовой проверки целостности всех ресурсов
def start_background_check(conn, interval: int) -> None:

    def periodic_check():
        while True:
            print(f"Начало фоновой проверки в {datetime.now()}")
            check_all_hashes(conn)
            threading.Event().wait(interval)
    if interval <= 0:
        print("Интервал должен быть положительным числом")
        return
    thread = threading.Thread(target=periodic_check, daemon=True)
    thread.start()
    print(f"Фоновая проверка запущена с интервалом {interval} секунд")