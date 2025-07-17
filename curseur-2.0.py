import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkcalendar import Calendar
import sqlite3
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime, timedelta
import matplotlib.dates as mdates
import sys
import csv
import os

DB_FILE = 'mesures_bme280.db'
CAPTEURS = ["abricot", "pêche", "prune"]
VOIES = ["temperature", "humidity", "pressure"]

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Afficheur BME280 - Multi-voies")
        self.geometry("1200x700")
        self.selected_device = tk.StringVar(value=CAPTEURS[0])
        self.available_dates = []
        self.timestamps = []

        self.create_widgets()
        self.load_data()

    def create_widgets(self):
        top_frame = tk.Frame(self)
        top_frame.pack(pady=5)

        tk.Label(top_frame, text="ESP:").pack(side=tk.LEFT, padx=5)
        ttk.OptionMenu(top_frame, self.selected_device, CAPTEURS[0], *CAPTEURS, command=self.on_device_change).pack(side=tk.LEFT, padx=5)

        ttk.Button(top_frame, text="Choisir une date", command=self.open_calendar).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Aujourd'hui", command=self.select_today).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Export CSV", command=self.export_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Quitter", command=self.close_app).pack(side=tk.LEFT, padx=5)

        self.fig, self.axes = plt.subplots(3, 1, figsize=(10, 6), sharex=True)
        self.fig.subplots_adjust(hspace=0.4)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def close_app(self):
        self.quit()
        self.destroy()
        sys.exit(0)

    def on_device_change(self, _=None):
        self.load_data()

    def open_calendar(self):
        if self.no_data:
            messagebox.showinfo("Aucun jour disponible", f"Aucune donnée pour '{self.selected_device.get()}'")
            return

        top = tk.Toplevel(self)
        cal = Calendar(top, selectmode='day', mindate=self.min_date.date(), maxdate=self.max_date.date())
        cal.pack(pady=10)

        all_days = set(self.min_date.date() + timedelta(days=i)
                       for i in range((self.max_date.date() - self.min_date.date()).days + 1))
        jours_vides = all_days - set(self.available_dates)

        for d in self.available_dates:
            cal.calevent_create(d, 'donnée', 'valide')
        for d in jours_vides:
            cal.calevent_create(d, 'vide', 'invalide')

        cal.tag_config('valide', background='lightgreen')
        cal.tag_config('invalide', background='lightgray')

        def confirm_date():
            selected = cal.selection_get()
            if selected in self.available_dates:
                self.plot_for_date(selected)
                top.destroy()
            else:
                messagebox.showwarning("Jour vide", f"Aucune donnée pour {selected}")

        ttk.Button(top, text="OK", command=confirm_date).pack(pady=5)

    def select_today(self):
        today = datetime.now().date()
        if today in self.available_dates:
            self.plot_for_date(today)

    def load_data(self):
        self.available_dates.clear()
        device = self.selected_device.get()
        capteurs = [f"{device}_BME1", f"{device}_BME2"]

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT timestamp FROM mesures WHERE device IN (?, ?) ORDER BY timestamp", capteurs)
        self.timestamps = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") for row in cursor.fetchall()]
        self.available_dates = sorted(set(dt.date() for dt in self.timestamps))

        if self.timestamps:
            self.min_date = self.timestamps[0]
            self.max_date = self.timestamps[-1]
            self.plot_for_date(self.min_date.date())
            self.no_data = False
        else:
            self.no_data = True
            self.min_date = datetime.now()
            self.max_date = datetime.now()
            for ax in self.axes:
                ax.clear()
                ax.set_title("Aucune donnée")
            self.canvas.draw()

        conn.close()

    def plot_for_date(self, selected_date):
        device = self.selected_device.get()
        capteurs = [f"{device}_BME1", f"{device}_BME2"]
        start = datetime.combine(selected_date, datetime.min.time())
        end = start + timedelta(days=1)

        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("""
            SELECT device, timestamp, temperature, humidity, pressure
            FROM mesures
            WHERE device IN (?, ?) AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp
        """, (*capteurs, start.isoformat(), end.isoformat()))
        rows = cur.fetchall()
        conn.close()

        data = {voie: {c: [] for c in capteurs} for voie in VOIES}

        for dev, ts, temp, hum, pres in rows:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            data["temperature"][dev].append((dt, temp))
            data["humidity"][dev].append((dt, hum))
            data["pressure"][dev].append((dt, pres))

        for i, voie in enumerate(VOIES):
            ax = self.axes[i]
            ax.clear()
            added = False
            for capteur in capteurs:
                points = data[voie][capteur]
                if points:
                    x, y = zip(*points)
                    ax.plot(x, y, label=capteur)
                    added = True
            ax.set_ylabel(voie.capitalize())
            if added:
                ax.legend()
            ax.grid(True)

        self.axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        self.axes[-1].set_xlabel("Heure")
        self.fig.suptitle(f"{device} - {selected_date}")
        self.canvas.draw()

    def export_csv(self):
        def do_export(start_date, end_date):
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("""
                SELECT id, device, timestamp, temperature, humidity, pressure
                FROM mesures
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp
            """, (start_date.isoformat(), (end_date + timedelta(days=1)).isoformat()))
            rows = cur.fetchall()
            conn.close()

            if not rows:
                messagebox.showinfo("Aucune donnée", "Aucune donnée dans l'intervalle spécifié.")
                return

            file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
            if not file_path:
                return

            with open(file_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["id", "device", "timestamp", "temperature", "humidity", "pressure"])
                for row in rows:
                    writer.writerow(row)

            self.log_action(f"Export CSV : {file_path} ({start_date} → {end_date})")
            messagebox.showinfo("Export terminé", f"{len(rows)} lignes exportées dans :\n{file_path}")

        self.open_date_range_dialog(do_export)

    def open_date_range_dialog(self, callback):
        top = tk.Toplevel(self)
        top.title("Choisir une plage de dates")

        tk.Label(top, text="Date de début :").pack()
        cal1 = Calendar(top, selectmode='day', date_pattern='yyyy-mm-dd')
        cal1.pack()

        tk.Label(top, text="Date de fin :").pack()
        cal2 = Calendar(top, selectmode='day', date_pattern='yyyy-mm-dd')
        cal2.pack()

        def submit():
            start = cal1.selection_get()
            end = cal2.selection_get()
            if start > end:
                messagebox.showerror("Erreur", "La date de début doit précéder la date de fin.")
                return
            top.destroy()
            callback(start, end)

        ttk.Button(top, text="Valider", command=submit).pack(pady=5)

    def log_action(self, message):
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"log-{datetime.now().strftime('%Y-%m-%d')}.txt")
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{now}] {message}\n")

if __name__ == "__main__":
    app = App()
    app.mainloop()
