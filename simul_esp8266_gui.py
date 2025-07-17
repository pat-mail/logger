import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
import random
import requests
import json
import threading
import time

SERVER_URL = "http://localhost:5000/receive_batch"

class SimulESPApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Simulateur ESP8266")
        self.geometry("400x330")

        self.create_widgets()
        self.running = False
        self.thread = None

    def create_widgets(self):
        ttk.Label(self, text="Nom de l'ESP simulé :").pack()
        self.device_var = tk.StringVar(value="mangue")
        ttk.Combobox(self, textvariable=self.device_var, values=["mangue", "carambole", "ananas"]).pack()

        ttk.Label(self, text="Date de départ (YYYY-MM-DD HH:MM:SS) :").pack()
        self.date_entry = ttk.Entry(self)
        self.date_entry.insert(0, datetime.now().strftime("%Y-%m-%d %H:00:00"))
        self.date_entry.pack()

        ttk.Label(self, text="Nombre de mesures (par capteur) :").pack()
        self.nb_entry = ttk.Entry(self)
        self.nb_entry.insert(0, "24")
        self.nb_entry.pack()

        self.loop_var = tk.BooleanVar()
        ttk.Checkbutton(self, text="Envoi périodique (1/min)", variable=self.loop_var).pack()

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=10)

        ttk.Button(btn_frame, text="Envoyer une fois", command=self.send_once).pack(side=tk.LEFT, padx=5)
        self.start_btn = ttk.Button(btn_frame, text="Démarrer périodique", command=self.start_loop)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="Stop", command=self.stop_loop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        self.status = ttk.Label(self, text="Prêt")
        self.status.pack()

    def start_loop(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self.send_loop, daemon=True)
            self.thread.start()
            self.status.config(text="Envoi périodique démarré.")
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)

    def stop_loop(self):
        self.running = False
        self.status.config(text="Envoi périodique arrêté.")
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

    def send_loop(self):
        while self.running:
            self.send_once()
            for _ in range(60):  # 1 minute en 60 pas
                if not self.running:
                    break
                time.sleep(1)

    def send_once(self):
        try:
            start_time = datetime.strptime(self.date_entry.get(), "%Y-%m-%d %H:%M:%S")
            n = int(self.nb_entry.get())
            device = self.device_var.get()

            payload = []
            for i in range(n):
                ts = (start_time + timedelta(minutes=5*i)).strftime("%Y-%m-%d %H:%M:%S")
                for bme in ["BME1", "BME2"]:
                    entry = {
                        "device": f"{device}_{bme}",
                        "temperature": round(22 + random.uniform(-2, 2), 2),
                        "humidity": round(50 + random.uniform(-10, 10), 2),
                        "pressure": round(1013 + random.uniform(-5, 5), 2),
                        "timestamp": ts
                    }
                    payload.append(entry)

            r = requests.post(SERVER_URL, json=payload)
            self.status.config(text=f"Envoyé ({len(payload)} mesures) - HTTP {r.status_code}")
        except Exception as e:
            self.status.config(text=f"Erreur : {e}")

    def on_close(self):
        self.stop_loop()
        self.destroy()

if __name__ == "__main__":
    app = SimulESPApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
