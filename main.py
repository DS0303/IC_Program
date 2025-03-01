import psycopg2
import tkinter
import functions as func

if __name__ == "__main__":
    # Подключение к базе данных
    try:
        conn = func.connect_to_db(
            dbname="ic_db",
            user="postgres",
            password="Qwerty123",
        )
    except func.psycopg2.Error as e:
        exit()

    # test_file = r"D:\123.txt"
    # file_hash = func.calculate_hash(test_file)
    # file_name = func.get_resource_name(test_file)
    # if file_hash:
    #     print(f"Хэш файла {test_file}: {file_hash}")
    # print(f"Имя файла: {file_name}")
    
    # test_folder = r"D:\Wireshark"
    # folder_hash = func.calculate_hash(test_folder)
    # folder_name = func.get_resource_name(test_folder)
    # if folder_hash:
    #     print(f"Хэш папки {test_folder}: {folder_hash}")
    # print(f"Имя папки: {folder_name}")

    # # Добавляем ресурсы в БД
    # func.add_resource_to_db(conn, test_file)
    # func.add_resource_to_db(conn, test_folder)

    func.update_all_hashes(conn)
    func.check_all_hashes(conn)

    # Закрываем соединение
    conn.close()