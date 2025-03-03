# main.py
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import functions as func

class IntegrityMonitoringApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Система контроля целостности")
        self.root.geometry("800x600")
        self.root.minsize(960, 500)  # Минимальный размер окна

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
        ttk.Label(bg_frame, text="Интервал (с):").pack(side="left")
        self.interval_var = tk.StringVar(value="10")
        ttk.Entry(bg_frame, textvariable=self.interval_var, width=5).pack(side="left", padx=2)
        ttk.Button(bg_frame, text="Запустить фоновую проверку", command=self.start_background_check).pack(side="left", padx=2)
        ttk.Button(bg_frame, text="Остановить", command=self.stop_background_check).pack(side="left", padx=2)

        # Центральная область - таблица ресурсов
        self.tree_frame = ttk.Frame(self.root)
        self.tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Столбец "Статус" теперь первый
        columns = ("status", "path", "name", "type", "added_date", "hash_date")
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show="headings")
        self.tree.heading("status", text="Статус")
        self.tree.heading("path", text="Путь")
        self.tree.heading("name", text="Имя")
        self.tree.heading("type", text="Тип")
        self.tree.heading("added_date", text="Добавлен")
        self.tree.heading("hash_date", text="Дата хэша")
        self.tree.column("status", width=80)
        self.tree.column("path", width=200)
        self.tree.column("name", width=100)
        self.tree.column("type", width=80)
        self.tree.column("added_date", width=120)
        self.tree.column("hash_date", width=120)

        # Скроллбар для таблицы (упаковываем перед таблицей)
        scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(fill="both", expand=True)

        # Обновляем таблицу после создания всех виджетов
        self.refresh_resources()

    def add_file(self):
        """Добавляет файл через диалог выбора."""
        path = filedialog.askopenfilename(title="Выберите файл", filetypes=[("Все файлы", "*.*")])
        if path:
            if func.add_resource_to_db(self.conn, path):
                self.refresh_resources()

    def add_folder(self):
        """Добавляет папку через диалог выбора."""
        path = filedialog.askdirectory(title="Выберите папку")
        if path:
            if func.add_resource_to_db(self.conn, path):
                self.refresh_resources()

    def remove_resource(self):
        """Удаляет выбранный ресурс."""
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

    def calculate_hashes(self):
        """Рассчитывает хэши для всех ресурсов."""
        func.update_all_hashes(self.conn)
        self.refresh_resources()

    def check_hashes(self):
        """Проверяет целостность всех ресурсов."""
        self.check_status = func.check_all_hashes(self.conn)
        self.refresh_resources()

    def start_background_check(self):
        """Запускает фоновую проверку."""
        try:
            interval = int(self.interval_var.get())
            if interval <= 0:
                raise ValueError("Интервал должен быть положительным")
            self.background_check_running = True
            func.start_background_check(self.conn, interval)
        except ValueError as e:
            messagebox.showerror("Ошибка", str(e))

    def stop_background_check(self):
        """Останавливает фоновую проверку."""
        self.background_check_running = False
        func.stop_background_check()

    def refresh_resources(self):
        """Обновляет таблицу ресурсов."""
        resources = func.list_all_resources(self.conn)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for res in resources:
            path, name, rtype, added, _, hash_date = res
            hash_date_str = hash_date.strftime("%Y-%m-%d %H:%M:%S") if hash_date else "Нет данных"
            added_str = added.strftime("%Y-%m-%d %H:%M:%S") if added else "Нет данных"
            # Определяем статус для отображения
            status = ""
            if path in self.check_status:
                if self.check_status[path] == "passed":
                    status = "✔"
                elif self.check_status[path] == "failed":
                    status = "✘"
                elif self.check_status[path] == "unavailable":
                    status = "N/A"
                elif self.check_status[path] == "no_hash":
                    status = "?"
            self.tree.insert("", "end", values=(status, path, name, rtype, added_str, hash_date_str))

    def on_closing(self):
        """Действия при закрытии окна."""
        self.conn.close()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = IntegrityMonitoringApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()