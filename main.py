import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import functions as func
import threading
from datetime import datetime

class IntegrityMonitoringApp:
    # Инициализация окна приложения
    def __init__(self, root):
        self.root = root
        self.root.title("Система контроля целостности")
        self.root.geometry("800x600")
        self.root.minsize(1045, 500)

        # Подключение к БД
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

        # Флаги и переменные 
        self.background_check_running = False # Флаг фоновой проверки
        self.check_status = {} # Словарь результатов проверки
        self.operation_running = False # Флаг работы текущей операции
        self.stop_operation_event = threading.Event() # Остановка текущей операции
        self.progress_window_active = False # Окно прогресса

        # Создание виджетов
        self.create_widgets()
        self.root.update()

    # Создание и размещение виджетов интерфейса
    def create_widgets(self):
        # Фрейм для кнопок
        button_frame = ttk.Frame(self.root)
        button_frame.pack(fill="x", padx=5, pady=5)
        
        # Кнопки
        self.add_file_button = ttk.Button(button_frame, text="Добавить файл", command=self.add_file)
        self.add_file_button.pack(side="left", padx=5)
        self.add_folder_button = ttk.Button(button_frame, text="Добавить папку", command=self.add_folder)
        self.add_folder_button.pack(side="left", padx=5)
        self.remove_button = ttk.Button(button_frame, text="Удалить", command=self.remove_resource)
        self.remove_button.pack(side="left", padx=5)
        self.calculate_button = ttk.Button(button_frame, text="Рассчитать хэши", command=self.calculate_hashes)
        self.calculate_button.pack(side="left", padx=5)
        self.check_button = ttk.Button(button_frame, text="Проверить целостность", command=self.check_hashes)
        self.check_button.pack(side="left", padx=5)

        # Фрейм для фоновой проверки
        bg_frame = ttk.Frame(button_frame)
        bg_frame.pack(side="left", padx=5)
        ttk.Label(bg_frame, text="Интервал:").pack(side="left")
        self.interval_var = tk.StringVar(value="10")
        ttk.Entry(bg_frame, textvariable=self.interval_var, width=5).pack(side="left", padx=2)
        self.interval_unit = tk.StringVar(value="сек.")
        ttk.Combobox(bg_frame, textvariable=self.interval_unit, values=["сек.", "мин.", "ч."], state="readonly", width=10).pack(side="left", padx=2)
        self.start_bg_button = ttk.Button(bg_frame, text="Запустить фоновую проверку", command=self.start_background_check)
        self.start_bg_button.pack(side="left", padx=2)

        # Фрейм таблицы ресурсов
        self.tree_frame = ttk.Frame(self.root)
        self.tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Настройка таблицы
        columns = ("status", "path", "name", "type", "added_date", "hash_date")
        self.tree = ttk.Treeview(self.tree_frame, columns=columns, show="headings")
        style = ttk.Style()
        # Теги для цветов
        style.configure("Treeview", font=("Arial", 10))
        self.tree.tag_configure("passed", background="lightgreen")
        self.tree.tag_configure("failed", background="lightcoral")
        self.tree.tag_configure("unavailable", background="lightgray")
        self.tree.tag_configure("oddrow", background="white")
        self.tree.tag_configure("evenrow", background="#F0F0F0")
        # Заголовки и ширина столбцов
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

        # Настройка полосы прокрутки
        scrollbar = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(fill="both", expand=True)

        # Обновление таблицы ресурсов
        self.refresh_resources()

    # Создание окна при выполнении операции 
    def create_progress_window(self, title, message):
        # Настройка окна
        progress_window = tk.Toplevel(self.root)
        progress_window.title(title)
        progress_window.geometry("300x100")
        progress_window.resizable(False, False)
        progress_window.transient(self.root)
        progress_window.grab_set()

        # Отображение текущей операции
        progress_label = ttk.Label(progress_window, text=message)
        progress_label.pack(pady=10)

        # Кнопка остановки операции
        stop_button = ttk.Button(progress_window, text="Остановить", command=lambda: self.stop_current_operation(progress_window))
        stop_button.pack(pady=10)

        # Отключение кнопок на основном окне при открытии окна выполнения операции
        self.disable_main_buttons()
        self.progress_window_active = True
        return progress_window

    # Создание окна таймера при фоновой проверке
    def create_timer_window(self, interval_in_seconds):
        # Настройка окна
        timer_window = tk.Toplevel(self.root)
        timer_window.title("Фоновая проверка")
        timer_window.geometry("300x150")
        timer_window.resizable(False, False)
        timer_window.transient(self.root)
        timer_window.grab_set()

        # Таймер до следующей проверки
        timer_label = ttk.Label(timer_window, text=f"До следующей проверки: {interval_in_seconds} сек")
        timer_label.pack(pady=10)

        # Кнопка остановить
        stop_button = ttk.Button(timer_window, text="Остановить", command=lambda: self.stop_background_check(timer_window))
        stop_button.pack(pady=10)

        # Отключение кнопок на основном окне при открытии окна выполнения операции
        self.disable_main_buttons()
        return timer_window, timer_label

    # Отключение кнопок на основном окне
    def disable_main_buttons(self):
        self.add_file_button.config(state="disabled")
        self.add_folder_button.config(state="disabled")
        self.remove_button.config(state="disabled")
        self.calculate_button.config(state="disabled")
        self.check_button.config(state="disabled")
        self.start_bg_button.config(state="disabled")

    # Включение кнопок на основном окне
    def enable_main_buttons(self):
        self.add_file_button.config(state="normal")
        self.add_folder_button.config(state="normal")
        self.remove_button.config(state="normal")
        self.calculate_button.config(state="normal")
        self.check_button.config(state="normal")
        self.start_bg_button.config(state="normal")

    # Остановка текущей операции
    def stop_current_operation(self, progress_window):
        self.stop_operation_event.set() # Установка флага остановки
        self.progress_window_active = False
        progress_window.destroy() # Закрытие окна прогресса
        self.enable_main_buttons() # Включение кнопок на основном окне
        self.operation_running = False

    # Оповещение о нарушении целостности при фоновой проверке
    def violations_alert(self, failed_count, failed_paths, timer_window=None):
        paths_str = "\n".join(failed_paths) # Список путей с нарушенияии
        # Вывод результатов и остановка фоновой проверки
        self.root.after(0, lambda: messagebox.showwarning("Нарушение целостности", f"Обнаружено нарушений целостности: {failed_count}\nФоновая проверка остановлена\n\nПути с нарушениями:\n{paths_str}"))
        self.root.after(0, lambda: self.stop_background_check(timer_window))
        self.root.after(0, self.check_hashes)

    # Добавление файла в БД
    def add_file(self):
        # Диалог выбора файла
        path = filedialog.askopenfilename(title="Выберите файл", filetypes=[("Все файлы", "*.*")])
        if path:
            if func.add_resource_to_db(self.conn, path):
                self.refresh_resources() # Обновление таблицы

    # Добавление папки в БД
    def add_folder(self):
        # Диалог выбора папки
        path = filedialog.askdirectory(title="Выберите папку")
        if path:
            if func.add_resource_to_db(self.conn, path):
                self.refresh_resources() # Обновление таблицы

    # Удаление ресурса из БД
    def remove_resource(self):
        # Получение выбранного ресурса по строке
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Предупреждение", "Выберите ресурс для удаления")
            return

        path = self.tree.item(selected[0])["values"][1] # Получение пути
        # Подтверждение удаления и удаление
        if messagebox.askyesno("Подтверждение", f"Удалить ресурс {path}?"):
            func.remove_resource_from_db(self.conn, path)
            if path in self.check_status:
                del self.check_status[path]
            self.refresh_resources() # Обновление таблицы

    # Расчет хэшей
    def calculate_hashes(self):
        # Проверка не выполняется ли уже операция
        if self.operation_running:
            return
        # Перезапись флагов
        self.operation_running = True
        self.stop_operation_event.clear()
        self.progress_window_active = False

        # Создание окна прогресса
        progress_window = self.create_progress_window("Расчёт хэшей", "Идёт расчёт эталонов...")
        
        # Запуск расчета хэшей
        def run_calculate():
            updated_count = func.update_all_hashes(self.conn, self.stop_operation_event)
            self.root.after(0, lambda: self.finish_operation(progress_window))

        # Запуск отдельного потока
        threading.Thread(target=run_calculate, daemon=True).start()

    # Проверка хэшей
    def check_hashes(self):
        # Проверка не выполняется ли уже операция
        if self.operation_running:
            return
        
        # Перезапись флагов
        self.operation_running = True
        self.stop_operation_event.clear()
        self.progress_window_active = False

        # Создание окна прогресса
        progress_window = self.create_progress_window("Проверка целостности", "Идёт проверка целостности...")

        # Запуск проверки
        def run_check():
            results = func.check_all_hashes(self.conn, self.stop_operation_event)
            self.root.after(0, lambda: self.finish_operation(progress_window, results))
        
        # Запуск отдельного потока
        threading.Thread(target=run_check, daemon=True).start()

    # Завершение текущей операции
    def finish_operation(self, progress_window, results=None):
        # Результаты проверки
        if results is not None:
            self.check_status = results
        self.refresh_resources() # Обновление таблицы
        self.progress_window_active = False
        progress_window.destroy() # Закрытии окна прогресса
        self.enable_main_buttons() # Включение кнопок на основном окне
        self.operation_running = False
        self.stop_operation_event.clear() # Сброс флага

    # Запуск фоновой проверки
    def start_background_check(self):
        try:
            # Получение интервала проверки
            interval = int(self.interval_var.get())
            if interval <= 0:
                raise ValueError("Интервал должен быть положительным")

            unit = self.interval_unit.get()
            if unit not in ["сек.", "мин.", "ч."]:
                raise ValueError("Некорректная единица измерения интервала")
            
            # Перевод интервала в секунды
            if unit == "сек.": interval_in_seconds = interval
            elif unit == "мин.":interval_in_seconds = interval * 60
            elif unit == "ч.": interval_in_seconds = interval * 3600

            self.background_check_running = True # Установка флага

            # Создание окна таймера
            timer_window, timer_label = self.create_timer_window(interval_in_seconds)

            # Обновление таймера и запуск проверки
            def update_timer(remaining_time):
                if not self.background_check_running:
                    return
                timer_label.config(text=f"До следующей проверки: {remaining_time} сек")
                if remaining_time > 0:
                    self.root.after(1000, lambda: update_timer(remaining_time - 1))
                else:
                    results = func.check_all_hashes(self.conn) # Запуск проверки хэшей
                    failed_paths = [path for path, status in results.items() if status == "failed"]
                    failed_count = len(failed_paths)
                    # Есть ли нарушения
                    if failed_count > 0:
                        self.violations_alert(failed_count, failed_paths, timer_window)
                    else:
                        self.root.after(0, self.refresh_resources)
                        self.root.after(0, lambda: update_timer(interval_in_seconds))
            
            # Запсук фоновой проверки
            func.start_background_check(
                self.conn,
                interval_in_seconds,
                lambda count, paths: self.violations_alert(count, paths, timer_window),
                lambda: self.root.after(0, self.refresh_resources)
            )
            update_timer(interval_in_seconds) # Запуск таймера

        except ValueError as e:
            messagebox.showerror("Ошибка", str(e))
            self.background_check_running = False

    # Остановка фоновой проверки
    def stop_background_check(self, timer_window=None):
        self.background_check_running = False
        func.stop_background_check()
        if timer_window:
            timer_window.destroy() # Закрытие окна таймера
            self.enable_main_buttons() # Включение кнопок на основном окне

    # Обновление таблицы ресурсов
    def refresh_resources(self):
        # Получения списка ресурсов
        resources = func.list_all_resources(self.conn)
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Заполнение таблицы
        for res in resources:
            path, name, rtype, added, _, hash_date = res
            # Форматирование дат
            hash_date_str = hash_date.strftime("%d-%m-%Y %H:%M:%S") if hash_date else "Нет данных"
            added_str = added.strftime("%d-%m-%Y %H:%M:%S") if added else "Нет данных"

            # Тип ресурса
            if rtype == "file":
                rtype = "Файл"
            elif rtype == "folder":
                rtype = "Папка"

            # Статус проверки и цвет строки
            status = ""
            tags = ("oddrow",) if len(self.tree.get_children()) % 2 == 0 else ("evenrow",)
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

    # Закрытие соединения с БД и закрытие главного окна
    def on_closing(self):
        self.conn.close()
        self.root.destroy()

# Запуск приложения
if __name__ == "__main__":
    root = tk.Tk()
    app = IntegrityMonitoringApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()