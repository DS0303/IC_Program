import hashlib
import os
import psycopg2
from datetime import datetime
import tkinter

# Хэш файла
def hash_file(file_path: str) -> str:
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
def hash_folder(folder_path: str) -> str:
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

# Выбор и расчет хэша для файла или папки
def calculate_hash(resource_path: str) -> str:
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

if __name__ == "__main__":
    test_file = r"D:\123.txt"
    file_hash = calculate_hash(test_file)
    if file_hash:
        print(f"Хэш файла {test_file}: {file_hash}")
    
    test_folder = r"D:\Wireshark"
    folder_hash = calculate_hash(test_folder)
    if folder_hash:
        print(f"Хэш папки {test_folder}: {folder_hash}")