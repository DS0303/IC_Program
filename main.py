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

    res = r'D:\2.txt'
    # func.add_resource_to_db(conn, res)

    # func.update_all_hashes(conn)
    # func.check_all_hashes(conn)
    func.list_all_resources(conn)

    func.start_background_check(conn, 10)
    input("Нажмите Enter для завершения (фоновая проверка остановится)...\n")

    # Закрываем соединение
    conn.close()