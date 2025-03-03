# main.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import functions as func

class IntegrityMonitoringApp:
    # Конструктор
    def __init__(self, root):
        self.root = root
        self.root.title("Система контроля целостности")
        self.root.geometry("800x600")
        self.root.minsize(1070, 500)  # Минимальный размер окна

        # Подключение к базе данных
        try:
            self.conn = func.connect_to_db(
                dbname="ic_db",
                user="postgres",
                password="Qwerty123",
            )
        except func.psycopg2.Error:
            messagebox.showerror("Ошибка", "Не удалось подключиться к базе данных")
            self.root.destroy()
            return

        # Переменная для управления фоновой проверкой
        self.background_check_running = False
        # Словарь для хранения статуса проверки каждого ресурса
        self.check_status = {}

        # Создание интерфейса
        self.create_widgets()
        self.root.update()  # Обновляем интерфейс после создания

    # Создание виджетов
    def create_widgets(self):
        # Верхняя панель с кнопками
        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill="x", padx=5, pady=5)

        # Две кнопки для добавления файла и папки
        ttk.Button(button_frame, text="Добавить файл", command=self.add_file).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Добавить папку", command=self.add_folder).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Удалить", command=self.remove_resource).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Рассчитать хэши", command=self.calculate_hashes).pack(side="left", padx=5)
        ttk.Button(button_frame, text="Проверить целостность", command=self.check_hashes).pack(side="left", padx=5)

        # Панель для фоновой проверки
        bg_frame = ttk.Frame(button_frame)
        bg_frame.pack(side="left", padx=5)
        ttk.Label(bg_frame, text="Интервал:").pack(side="left")
        self.interval_var = tk.StringVar(value="10")
        ttk.Entry(bg_frame, textvariable=self.interval_var, width=5).pack(side="left", padx=2)
        # Добавляем выпадающий список для выбора единиц измерения
        self.interval_unit = tk.StringVar(value="Секунды")
        ttk.Combobox(bg_frame, textvariable=self.interval_unit, values=["сек.", "мин.", "ч."], state="readonly", width=10).pack(side="left", padx=2)
        ttk.Button(bg_frame, text="Запустить фоновую проверку", command=self.start_background_check).pack(side="left", padx=2)
        ttk.Button(bg_frame, text="Остановить", command=self.stop_background_check).pack(side="left", padx=2)

        # Центральная область - таблица ресурсов
        self.tree_frame = ttk.Frame(self.root)
        self.tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Столбец "Статус" теперь первый
        columns = ("status", "path", "name", "type", "added_date", "hash_date")
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show="headings")
        # Устанавливаем тему и шрифт
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", font=("Arial", 10))
        # Теги для цветовой разметки
        self.tree.tag_configure("passed", background="lightgreen")
        self.tree.tag_configure("failed", background="lightcoral")
        self.tree.tag_configure("unavailable", background="lightgray")
        # Заголовки столбцов
        self.tree.heading("status", text="Статус")
        self.tree.heading("path", text="Путь")
        self.tree.heading("name", text="Имя")
        self.tree.heading("type", text="Тип")
        self.tree.heading("added_date", text="Добавлен")
        self.tree.heading("hash_date", text="Дата хэша")
        self.tree.column("status", width=1, anchor=tk.CENTER)
        self.tree.column("path", width=200)
        self.tree.column("name", width=100)
        self.tree.column("type", width=1)
        self.tree.column("added_date", width=12)
        self.tree.column("hash_date", width=12)

        # Скроллбар для таблицы
        scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(fill="both", expand=True)

        # Обновляем таблицу после создания всех виджетов
        self.refresh_resources()

    # Добавление файлов
    def add_file(self):
        path = filedialog.askopenfilename(title="Выберите файл", filetypes=[("Все файлы", "*.*")])
        if path:
            if func.add_resource_to_db(self.conn, path):
                self.refresh_resources()

    # Добавление папок
    def add_folder(self):
        path = filedialog.askdirectory(title="Выберите папку")
        if path:
            if func.add_resource_to_db(self.conn, path):
                self.refresh_resources()

    # Удаление ресурса
    def remove_resource(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите ресурс для удаления")
            return

        path = self.tree.item(selected[0])["values"][1]  # Путь на втором месте из-за столбца "Статус"
        if messagebox.askyesno("Подтверждение", f"Удалить ресурс {path}?"):
            func.remove_resource_from_db(self.conn, path)
            # Удаляем статус проверки для этого ресурса
            if path in self.check_status:
                del self.check_status[path]
            self.refresh_resources()

    # Рассчет хэшей
    def calculate_hashes(self):
        func.update_all_hashes(self.conn)
        self.refresh_resources()

    # Проверка хэшей
    def check_hashes(self):
        self.check_status = func.check_all_hashes(self.conn)
        self.refresh_resources()

    # Запуск фоновой проверки
    def start_background_check(self):
        try:
            interval = int(self.interval_var.get())
            if interval <= 0:
                raise ValueError("Интервал должен быть положительным")

            # Конвертируем интервал в секунды в зависимости от выбранной единицы
            unit = self.interval_unit.get()
            if unit == "Секунды":
                interval_in_seconds = interval
            elif unit == "Минуты":
                interval_in_seconds = interval * 60
            elif unit == "Часы":
                interval_in_seconds = interval * 3600

            self.background_check_running = True
            func.start_background_check(self.conn, interval_in_seconds)
        except ValueError as e:
            messagebox.showerror("Ошибка", str(e))

    # Остановка фоновой проверки
    def stop_background_check(self):
        self.background_check_running = False
        func.stop_background_check()

    # Обновление списка ресурсов
    def refresh_resources(self):
        resources = func.list_all_resources(self.conn)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for res in resources:
            path, name, rtype, added, _, hash_date = res
            hash_date_str = hash_date.strftime("%d-%m-%Y %H:%M:%S") if hash_date else "Нет данных"
            added_str = added.strftime("%d-%m-%Y %H:%M:%S") if added else "Нет данных"

            # Определить тип ресурса
            if rtype == "file":
                rtype = "Файл"
            elif rtype == "folder":
                rtype = "Папка"

            # Определяем статус для отображения
            status = ""
            tags = ()
            if path in self.check_status:
                if self.check_status[path] == "passed":
                    status = "\u2714"
                    tags = ("passed",)
                elif self.check_status[path] == "failed":
                    status = "\u2718"
                    tags = ("failed",)
                elif self.check_status[path] == "unavailable":
                    status = "N/A"
                    tags = ("unavailable",)
                elif self.check_status[path] == "no_hash":
                    status = "\u003F"
                    tags = ("unavailable",)
            self.tree.insert("", "end", values=(status, path, name, rtype, added_str, hash_date_str), tags=tags)

    # Закрытие окна
    def on_closing(self):
        self.conn.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = IntegrityMonitoringApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()