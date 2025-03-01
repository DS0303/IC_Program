import hashlib
import os
import psycopg2
from typing import Optional
from datetime import datetime

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