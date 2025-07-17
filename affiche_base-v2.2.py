import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, timedelta
import sqlite3
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

DB_FILE = "mesures_bme280.db"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Affichage données BME280")
        self.geometry("900x600")

        self.selected_device = tk.StringVar()
        self.selected_channels = {
            "temperature": tk.BooleanVar(value=True),
            "humidity": tk.BooleanVar(value=True),
            "pressure": tk.BooleanVar(value=True),
        }
        self.current_date = None
        self.timestamps = []
        self.available_dates = []
        self.min_date = None
        self.max_date = None
        self.no_data = True

        self.accel_speed = 0  # 0=normal, 1=rapide, 2=très rapide
        self.auto_scroll_job = None

        self.create_widgets()
        self.refresh_devices()

    def create_widgets(self):
        top_frame = ttk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

        ttk.Label(top_frame, text="ESP:").pack(side=tk.LEFT)
        self.device_combo = ttk.Combobox(top_frame, state="readonly", width=15)
        self.device_combo.pack(side=tk.LEFT, padx=5)
        self.device_combo.bind("<<ComboboxSelected>>", lambda e: self.on_device_change())

        for voie in self.selected_channels:
            cb = ttk.Checkbutton(top_frame, text=voie.capitalize(),
                                 variable=self.selected_channels[voie],
                                 command=self.refresh_plot)
            cb.pack(side=tk.LEFT, padx=3)

        btn_week_back = ttk.Button(top_frame, text="<<", width=3)
        btn_week_back.pack(side=tk.LEFT, padx=2)
        btn_week_back.bind("<ButtonPress-1>", lambda e: self.start_auto_scroll(-7))
        btn_week_back.bind("<ButtonRelease-1>", lambda e: self.stop_auto_scroll())

        btn_day_back = ttk.Button(top_frame, text="<", width=3)
        btn_day_back.pack(side=tk.LEFT, padx=2)
        btn_day_back.bind("<ButtonPress-1>", lambda e: self.start_auto_scroll(-1))
        btn_day_back.bind("<ButtonRelease-1>", lambda e: self.stop_auto_scroll())

        btn_today = ttk.Button(top_frame, text="Aujourd'hui", command=self.select_today)
        btn_today.pack(side=tk.LEFT, padx=5)

        btn_day_fwd = ttk.Button(top_frame, text=">", width=3)
        btn_day_fwd.pack(side=tk.LEFT, padx=2)
        btn_day_fwd.bind("<ButtonPress-1>", lambda e: self.start_auto_scroll(1))
        btn_day_fwd.bind("<ButtonRelease-1>", lambda e: self.stop_auto_scroll())

        # ** Nouveau bouton avance rapide par semaine **
        btn_week_fwd = ttk.Button(top_frame, text=">>", width=3)
        btn_week_fwd.pack(side=tk.LEFT, padx=2)
        btn_week_fwd.bind("<ButtonPress-1>", lambda e: self.start_auto_scroll(7))
        btn_week_fwd.bind("<ButtonRelease-1>", lambda e: self.stop_auto_scroll())

        btn_quit = ttk.Button(top_frame, text="Quitter", command=self.quit)
        btn_quit.pack(side=tk.RIGHT, padx=10)

        # Champ date saisie + bouton
        ttk.Label(top_frame, text="Aller à la date (YYYY-MM-DD):").pack(side=tk.LEFT, padx=(20, 3))
        self.date_entry = ttk.Entry(top_frame, width=12)
        self.date_entry.pack(side=tk.LEFT)
        # Lier la touche Entrée à la fonction go_to_date
        self.date_entry.bind("<Return>", lambda e: self.go_to_date())
        btn_go_date = ttk.Button(top_frame, text="Go", command=self.go_to_date)
        btn_go_date.pack(side=tk.LEFT, padx=3)

        # (Le reste inchangé)


        # Figure matplotlib
        self.fig, self.axes = plt.subplots(3, 1, figsize=(8, 6), sharex=True)
        plt.subplots_adjust(top=0.88, bottom=0.1, left=0.1, right=0.95, hspace=0.35)

        for ax, voie in zip(self.axes, ["temperature", "humidity", "pressure"]):
            ax.set_ylabel(voie.capitalize())
            ax.grid(True)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def refresh_devices(self):
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT device FROM mesures ORDER BY device")
        devices = [row[0] for row in cursor.fetchall()]
        conn.close()
        # Accepter tous les devices y compris simulés
        self.device_combo['values'] = devices
        if devices:
            self.device_combo.current(0)
            self.selected_device.set(devices[0])
            self.on_device_change()

    def on_device_change(self):
        self.load_data()

    def load_data(self):
        self.available_dates.clear()
        device = self.device_combo.get()
        if not device:
            return
        capteurs = [f"{device}_BME1", f"{device}_BME2"]

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT timestamp, temperature, humidity, pressure
            FROM mesures
            WHERE device=?
            ORDER BY timestamp
        """, (device,))
        rows = cursor.fetchall()
        conn.close()

        self.timestamps = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") for row in rows]
        self.available_dates = sorted(set(ts.date() for ts in self.timestamps))

        if self.timestamps:
            self.min_date = self.timestamps[0]
            self.max_date = self.timestamps[-1]
            self.no_data = False
            # Affiche la première date ou aujourd'hui si présente
            date_to_show = datetime.now().date() if datetime.now().date() in self.available_dates else self.min_date.date()
            self.plot_for_date(date_to_show)
        else:
            self.no_data = True
            self.min_date = datetime.now()
            self.max_date = datetime.now()
            for ax in self.axes:
                ax.clear()
                ax.set_title("Aucune donnée")
            self.canvas.draw()

    def plot_for_date(self, selected_date):
        self.current_date = selected_date
        device = self.device_combo.get()
        if not device:
            return

        start = datetime.combine(selected_date, datetime.min.time())
        end = start + timedelta(days=1)

        self.plot_data(device, start, end)

    def plot_data(self, device, start, end):
        capteur1 = f"{device}_BME1"
        capteur2 = f"{device}_BME2"

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(f"""
            SELECT timestamp, temperature, humidity, pressure
            FROM mesures
            WHERE device=?
              AND timestamp >= ?
              AND timestamp < ?
            ORDER BY timestamp
        """, (device, start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")))
        rows = cursor.fetchall()
        conn.close()

        self.fig.suptitle(f"{device} - {start.date()}", fontsize=14)

        # Préparation des listes
        times = [datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S") for row in rows]
        temperature = [row[1] for row in rows]
        humidity = [row[2] for row in rows]
        pressure = [row[3] for row in rows]

        # On efface les graphiques
        for ax in self.axes:
            ax.clear()

        # On affiche les données selon sélection des voies
        if self.selected_channels["temperature"].get():
            self.axes[0].plot(times, temperature, label="Température", color="red")
            self.axes[0].set_ylabel("Température (°C)")
            self.axes[0].grid(True)
        else:
            self.axes[0].set_ylabel("")
        if self.selected_channels["humidity"].get():
            self.axes[1].plot(times, humidity, label="Humidité", color="blue")
            self.axes[1].set_ylabel("Humidité (%)")
            self.axes[1].grid(True)
        else:
            self.axes[1].set_ylabel("")
        if self.selected_channels["pressure"].get():
            self.axes[2].plot(times, pressure, label="Pression", color="green")
            self.axes[2].set_ylabel("Pression (hPa)")
            self.axes[2].grid(True)
        else:
            self.axes[2].set_ylabel("")

        for ax in self.axes:
            ax.set_xlabel("Heure")
            ax.legend(loc="upper right")

        self.canvas.draw()

    def refresh_plot(self):
        if self.current_date:
            self.plot_for_date(self.current_date)

    def previous_day(self):
        if self.current_date:
            prev = self.current_date - timedelta(days=1)
            self.plot_for_date(prev)

    def next_day(self):
        if self.current_date:
            nxt = self.current_date + timedelta(days=1)
            self.plot_for_date(nxt)

    def previous_week(self):
        if self.current_date:
            prev = self.current_date - timedelta(days=7)
            self.plot_for_date(prev)

    def select_today(self):
        today = datetime.now().date()
        self.plot_for_date(today)

    def go_to_date(self):
        date_str = self.date_entry.get()
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror("Erreur", "Date invalide. Utilisez le format YYYY-MM-DD.")
            return

        if self.min_date and self.max_date:
            min_d = self.min_date.date() if isinstance(self.min_date, datetime) else self.min_date
            max_d = self.max_date.date() if isinstance(self.max_date, datetime) else self.max_date
            if d < min_d or d > max_d:
                messagebox.showerror("Erreur", f"La date doit être comprise entre {min_d} et {max_d}.")
                return

        self.plot_for_date(d)

    def start_auto_scroll(self, delta_days):
        self.accel_speed = 0
        self._auto_scroll_step(delta_days)

    def _auto_scroll_step(self, delta_days):
        if not self.current_date:
            return
        speed_multipliers = [1, 5, 25]
        multiplier = speed_multipliers[min(self.accel_speed, 2)]

        new_date = self.current_date + timedelta(days=delta_days * multiplier)
        # Clamp date between min_date and max_date
        if self.min_date and self.max_date:
            if new_date < self.min_date.date():
                new_date = self.min_date.date()
            elif new_date > self.max_date.date():
                new_date = self.max_date.date()

        self.plot_for_date(new_date)

        self.accel_speed = min(self.accel_speed + 1, 2)  # accélère à chaque appel

        self.auto_scroll_job = self.after(500, self._auto_scroll_step, delta_days)

    def stop_auto_scroll(self):
        if self.auto_scroll_job:
            self.after_cancel(self.auto_scroll_job)
            self.auto_scroll_job = None
            self.accel_speed = 0

if __name__ == "__main__":
    app = App()
    app.mainloop()
