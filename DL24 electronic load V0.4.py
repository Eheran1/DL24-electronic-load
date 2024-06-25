# -*- coding: utf-8 -*-
"""
Created on Thu Sep 14 19:04:29 2023

@author: Leo

pip install -U git+https://github.com/KrystianD/dl24-electronic-load
"""

import tkinter as tk
from tkinter import ttk, filedialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import os
import csv
import datetime
import time
from dl24 import DL24
from matplotlib.ticker import FormatStrFormatter
import threading
import queue
from matplotlib.figure import Figure

COM_Port = "COM3"
Voltage_array = []
Current_array = []
Charge_array = [0]
Energy_array = [0]

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("DL24 Data Collection and Plotting")
        self.com_port_lock = threading.Lock()
        # Variables
        self.output_var = tk.StringVar()
        self.append_var = tk.BooleanVar()
        self.debug_var = tk.BooleanVar()
        self.override_var = tk.BooleanVar()
        
        # Lists for storing recorded data
        self.date_series = []
        self.voltage_series = []
        self.current_series = []
        self.energy_series = []
        self.charge_series = []
    
        # Automatic filename setup for the CSV output
        current_datetime = datetime.datetime.now().strftime('%Y.%m.%d %H-%M-%S')
        self.output_var.set(f"DL24 {current_datetime}.csv")
    
        ttk.Label(root, text="Output CSV:").grid(row=0, column=0, sticky="e")
        ttk.Entry(root, textvariable=self.output_var).grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        ttk.Button(root, text="Browse", command=self.browse_output).grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Checkbutton(root, text="Append", variable=self.append_var).grid(row=1, column=1, sticky="w")
        ttk.Checkbutton(root, text="Override", variable=self.override_var).grid(row=1, column=1)
        ttk.Checkbutton(root, text="Debug", variable=self.debug_var).grid(row=2, column=1, sticky="w")
        
    
        # Data collection buttons
        self.start_btn = ttk.Button(root, text="Start", command=self.toggle_data_collection)
        self.start_btn.grid(row=3, column=0, columnspan=3, pady=10, sticky="ew")
        

        # DL24 Management Widgets with current settings
        self.current_var = tk.StringVar(root, value="Current setting")
        ttk.Label(root, textvariable=self.current_var).grid(row=6, column=0, sticky="e")
        self.current_entry = ttk.Entry(root)
        self.current_entry.grid(row=6, column=1, padx=10, pady=5, sticky="ew")
        ttk.Button(root, text="Set", command=self.set_dl24_current).grid(row=6, column=2, padx=5, pady=5)
    
        self.voltage_cutoff_var = tk.StringVar(root, value="Voltage cutoff setting")
        ttk.Label(root, textvariable=self.voltage_cutoff_var).grid(row=7, column=0, sticky="e")
        self.voltage_cutoff_entry = ttk.Entry(root)
        self.voltage_cutoff_entry.grid(row=7, column=1, padx=10, pady=5, sticky="ew")
        ttk.Button(root, text="Set", command=self.set_dl24_voltage_cutoff).grid(row=7, column=2, padx=5, pady=5)
    
        self.timer_var = tk.StringVar(root, value="Timer setting")
        ttk.Label(root, textvariable=self.timer_var).grid(row=8, column=0, sticky="e")
        self.timer_entry = ttk.Entry(root)
        self.timer_entry.grid(row=8, column=1, padx=10, pady=5, sticky="ew")
        ttk.Button(root, text="Set", command=self.set_dl24_timer).grid(row=8, column=2, padx=5, pady=5)
    
        # DL24 enable/disable merged button
        self.dl24_button_state = False  # False = disabled, True = enabled
        self.dl24_toggle_btn = ttk.Button(root, text="Enable DL24", command=self.toggle_dl24)
        self.dl24_toggle_btn.grid(row=9, column=0, columnspan=2, padx=5, pady=5, sticky="ew")
    
        ttk.Button(root, text="Reset DL24", command=self.reset_dl24).grid(row=9, column=2, padx=5, pady=5, sticky="ew")
        
        ttk.Button(root, text="Read DL24", command=self.read_dl24).grid(row=10, column=0, columnspan=3, padx=5, pady=5, sticky="ew")
        
        self.dl24_status = ttk.Label(root, text="DL24 Status: Awaiting input")
        self.dl24_status.grid(row=11, column=0, columnspan=3, padx=10, pady=10, sticky="ew")
        
        self.root.columnconfigure(1, weight=1)
        
        # Data collection attributes
        self.csvfile = None
        self.wr = None
        self.collecting_data = False
        self.data_collection_thread = None
        
        # Plotting by default
        
        self.fig = Figure(figsize=(8.5, 7))
        self.ax1 = self.fig.add_subplot(111)
        self.ax2 = self.ax1.twinx()
        self.ax3 = self.ax1.twinx()
        self.ax4 = self.ax1.twinx()
        
        # Move the tick labels of ax3 to the left of its own spine
        self.ax3.yaxis.tick_left()
        self.ax3.yaxis.set_label_position("left")
        self.ax3.tick_params(axis='y', which='both', direction='out', colors='blue')
        self.ax3.spines["left"].set_position(("axes", 1.0))
        
        self.ax4.spines["right"].set_position(("axes", 0.00))
        self.ax4.tick_params(axis='y', which='both', direction='out', colors='orange')
        
        self.fig.set_size_inches(8.5, 7)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=12, column=0, columnspan=3, padx=10, pady=10, sticky="ew")
        
        # Initialize the queue to store data from the data collection thread
        self.data_queue = queue.Queue()
        self.pending_set_actions = []
        time.sleep(1)
        self.update_dl24_settings()
        
        # Additional attributes for handling "set" actions for DL24
        
        print("App initialized.")
        
    def toggle_dl24(self):
        if self.dl24_button_state:
            self._with_dl24(self._disable)
            self.dl24_toggle_btn["text"] = "Enable DL24"
            self.dl24_button_state = False
        else:
            self._with_dl24(self._enable)
            self.dl24_toggle_btn["text"] = "Disable DL24"
            self.dl24_button_state = True
        
    def browse_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if path:
            self.output_var.set(path)
        
    def toggle_data_collection(self):
        if self.collecting_data:
            self.collecting_data = False
            self.start_btn["text"] = "Start"
            self.stop_data_collection()  # Stopping data collection
        else:
            self.collecting_data = True
            self.start_btn["text"] = "Stop"
            self.data_collection_thread = threading.Thread(target=self.collect_data)
            self.data_collection_thread.start()  # Starting data collection in a new thread
            self.root.after(1000, self.check_data_queue)  # Start checking the data queue
    
    def start_data_collection(self):
        if not self.collecting_data:
            self.collecting_data = True
            self.start_btn["state"] = tk.DISABLED
            self.data_queue = queue.Queue()
            self.data_collection_thread = threading.Thread(target=self.collect_data)
            self.data_collection_thread.start()
            self.root.after(1000, self.check_data_queue)
        else:
            self.start_btn["state"] = tk.NORMAL
            self.collecting_data = False
    
    def stop_data_collection(self):
        self.collecting_data = False
        if self.csvfile:
            self.csvfile.close()
            self.csvfile = None
            self.wr = None
        # Join the thread to ensure it stops cleanly
        self.data_collection_thread.join()
    
    def collect_data(self):
        while self.collecting_data:
            with self.com_port_lock:
                try:
                    with DL24(COM_Port) as dl24:
                        voltage = dl24.get_voltage()
                        current = dl24.get_current()
                        temp = dl24.get_temp()
                        energy = dl24.get_energy()
                        charge = dl24.get_charge()
                        on_time = dl24.get_time()
                        t = datetime.datetime.now()
                        Power = voltage * current   
                        
                        Voltage_array.append(voltage)
                        Current_array.append(current)
                        if len(self.date_series) > 0:
                            dt = (t - self.date_series[-1]).total_seconds()     # s
                            Charge = (current * dt) / 3.6 + Charge_array[-1]    # mAh
                            Energy = (Power * dt) / 3600. + Energy_array[-1]    # Wh
                            Charge_array.append(Charge)
                            Energy_array.append(Energy)
                        else:
                            Charge = charge
                            Energy = energy      
                        
                        
                        
                        data_to_plot = (t, voltage, current, Energy, Charge, temp)
                        self.data_queue.put(data_to_plot)
                except Exception as e:
                    print(f"Error while collecting data: {e}")
                
            out_path = self.output_var.get()
            if out_path:
                exists = os.path.exists(out_path)
                if self.csvfile is None:
                    if self.append_var.get() and exists:
                        self.csvfile = open(out_path, 'a', newline='')
                    else:
                        self.csvfile = open(out_path, 'w', newline='')
                        self.wr = csv.writer(self.csvfile)
                        self.wr.writerow(['date', 'voltage', 'current', 'Power', 'Energy', 'Charge', 'temp', 'time_seconds', 'time_str'])
                if self.wr:
                    days = on_time.days
                    seconds = on_time.seconds
                    hours = seconds // 3600
                    minutes = (seconds // 60) % 60
                    seconds = seconds % 60
                    time_sec = int(on_time.total_seconds())
                    time_str = f"{days:01d}d {hours:02d}:{minutes:02d}:{seconds:02d}"
                    data = [
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        f"{voltage:.3f}",
                        f"{current:.3f}",
                        f"{Power:.2f}",
                        f"{Energy:.3f}",
                        f"{Charge:.1f}",
                        f"{temp:.0f}",
                        f"{time_sec}",
                        time_str,
                    ]
                    self.wr.writerow(data)
                    self.csvfile.flush()
            
            time.sleep(0.5)  # read frequency
    
    def check_data_queue(self):
        # Handle DL24 "set" actions if any
        for action in self.pending_set_actions:
            action()
        self.pending_set_actions.clear()
        try:
            #print("collecting_data in check_data_queue()", self.collecting_data)
            # Non-blocking get from the queue
            dt, voltage, current, energy, charge, temp = self.data_queue.get_nowait()
            # Update the series data used for plotting
            self.date_series.append(dt)
            self.voltage_series.append(voltage)
            self.current_series.append(current)
            self.energy_series.append(energy)
            self.charge_series.append(charge)
            # Update the plot
            self.plot_data()
            timestring = dt.strftime("%Y.%m.%d %H:%M:%S.%f")[:-4] # -4 = last 4 decimal places discarded = 2 remain
            data_str = f"{timestring} | {voltage:6.03f} V | {current:6.3f} A | {voltage * current:6.2f} W | {energy:6.3f} Wh | {charge:7.1f} mAh | {temp:4.1f} °C"
            print(data_str)  # Printing live data to the console
            
        except queue.Empty:
            pass
        if self.collecting_data:
            #print("check_data_queue collecting_data, wait")
            self.root.after(500, self.check_data_queue)
    
    def set_dl24_current(self):
        value = float(self.current_entry.get())
        
        def operation(dl24):
            try:
                self._set_current(dl24, value)
                # The after() method in tkinter schedules a function to be run in the main thread. 
                # By using a delay of 0, it means the function will be scheduled to run as soon as possible.
                self.root.after(0, lambda: self.dl24_status.config(text=f"Current set to {value} A"))
                self.root.after(0, self.update_dl24_settings)
            except Exception as e:
                print(f"Error while setting current: {e}")
        
        self.pending_set_actions.append(lambda: self._with_dl24(operation))
    
    def set_dl24_voltage_cutoff(self):
        value = float(self.voltage_cutoff_entry.get())
        def operation(dl24):
            self._set_voltage_cutoff(dl24, value)
            self.root.after(0, lambda: self.dl24_status.config(text=f"Voltage cutoff set to {value} V"))
            self.root.after(0, self.update_dl24_settings)
        
        self.pending_set_actions.append(lambda: self._with_dl24(operation))
    
    def set_dl24_timer(self):
        value_str = self.timer_entry.get()
        try:
            # try to interpret the input as pure seconds first
            value = float(value_str)
        except ValueError:
            # if not, try to interpret it as HH:MM:SS
            hours, minutes, seconds = map(int, value_str.split(':'))
            value = hours * 3600 + minutes * 60 + seconds
    
        def operation(dl24):
            self._set_timer(dl24, value)
            self.root.after(0, lambda: self.dl24_status.config(text=f"Timer set to {value} seconds"))
            self.root.after(0, lambda: self.timer_var.set(f"Timer setting: {self.timedelta_to_str(datetime.timedelta(seconds=value))}"))
            self.root.after(0, self.update_dl24_settings)
        
        self.pending_set_actions.append(lambda: self._with_dl24(operation))
    
    def _with_dl24(self, operation):
        with self.com_port_lock:
            try:
                with DL24(COM_Port) as dl24:
                    operation(dl24)
            except Exception as e:
                print(f"Error while executing operation with DL24: {e}")
    
    def update_dl24_settings(self):
        def operation(dl24):
            current_limit = dl24.get_current_limit()
            voltage = dl24.get_voltage_cutoff()
            timer = dl24.get_timer()
        
            self.current_var.set(f"Current setting: {current_limit} A")
            self.voltage_cutoff_var.set(f"Voltage cutoff setting: {voltage} V")
            self.timer_var.set(f"Timer setting: {timer} seconds")
        
        self._with_dl24(operation)
    
    def enable_dl24(self):
        def operation(dl24):
            self._enable(dl24)
            self.dl24_status["text"] = "DL24 Enabled"
            
        self._with_dl24(operation)
    
    def disable_dl24(self):
        def operation(dl24):
            self._disable(dl24)
            self.dl24_status["text"] = "DL24 Disabled"
        self._with_dl24(operation)
    
    def reset_dl24(self):
        def operation(dl24):
            self._reset_counters(dl24)
            self.dl24_status["text"] = "DL24 Counters Reset"
    
            # Clear the stored data
            self.date_series.clear()
            self.voltage_series.clear()
            self.current_series.clear()
            self.energy_series.clear()
            self.charge_series.clear()
    
            # Update the plot
            self.plot_data()
    
        self._with_dl24(operation)
    
    def read_dl24(self):
        def operation(dl24):
            self._read(dl24)
            
        self._with_dl24(operation)
    
    def _set_current(self, dl24, value):
        try:
            dl24.set_current(value)
            print("set_current ", value)
        except Exception as e:
            print(f"Error while setting current in DL24: {e}")
    
    def _set_voltage_cutoff(self, dl24, value):
        dl24.set_voltage_cutoff(value)
        print("set_voltage_cutoff", value)
    
    def _set_timer(self, dl24, value):
        td = datetime.timedelta(seconds=value)
        dl24.set_timer(td)
        print("set_timer", td)
    
    def _enable(self, dl24):
        dl24.enable()
        print("enable")
    
    def _disable(self, dl24):
        dl24.disable()
        print("disable")
    
    def _reset_counters(self, dl24):
        dl24.reset_counters()
        print("reset_counters")
    def timedelta_to_str(self, td):
        days = td.days
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d. {hours:02}:{minutes:02}:{seconds:02}"

    def _read(self, dl24):
        is_on = dl24.get_is_on()
        voltage = dl24.get_voltage()
        current = dl24.get_current()
        energy = dl24.get_energy()
        charge = dl24.get_charge()
        time_DL24 = dl24.get_time()
        temp = dl24.get_temp()
        current_limit = dl24.get_current_limit()
        voltage_cutoff = dl24.get_voltage_cutoff()
        timer = dl24.get_timer()
    
        print(self.format_value("enabled", "yes" if is_on else "no", None))
        print(self.format_value("voltage", voltage, "V"))
        print(self.format_value("current", current, "A"))
        print(self.format_value("energy", energy, "Wh"))
        print(self.format_value("charge", charge, "Ah"))
        print(self.format_value("time", self.timedelta_to_str(time_DL24), None))
        print(self.format_value("temperature", temp, "°C"))
        print(self.format_value("current_limit", current_limit, "A"))
        print(self.format_value("voltage_cutoff", voltage_cutoff, "V"))
        print(self.format_value("timer", self.timedelta_to_str(timer), None))


    def format_value(self, name, value, unit):
        value_str = f"{value}"
        value_str += f" {unit or '': <3s}"
        return f"{name: >20s}: {value_str: >12s}"
            

            
                
    def plot_data(self):
        # Clear axes
        self.ax1.clear()
        self.ax2.clear()
        self.ax3.clear()
        self.ax4.clear()
        
        # Move the tick labels of ax3 to the left of its own spine
        self.ax3.yaxis.tick_left()
        self.ax3.yaxis.set_label_position("left")
        self.ax3.tick_params(axis='y', which='both', direction='out', colors='blue')
        self.ax3.spines["left"].set_position(("axes", 1.0))
        
        self.ax4.spines["right"].set_position(("axes", 0.00))
        self.ax4.tick_params(axis='y', which='both', direction='out', colors='orange')
        
        
        # Plotting current over time on primary axis (left side)
        self.ax1.plot(self.date_series, self.voltage_series, color='green', label='Voltage')
        self.ax2.plot(self.date_series, self.current_series, color='red', label='Current')
        self.ax3.plot(self.date_series, self.charge_series, color='blue', linestyle='--', label='Charge')
        self.ax4.plot(self.date_series, self.energy_series, color='orange', linestyle='-.', label='Energy')
        
        # Set axes colors to match plot colors
        self.ax1.tick_params(axis='y', colors='green')
        self.ax2.tick_params(axis='y', colors='red')
        self.ax3.tick_params(axis='y', colors='blue')
        self.ax4.tick_params(axis='y', colors='orange')
        
        # Set formatting for the axes
        self.ax1.yaxis.set_major_formatter(FormatStrFormatter('%g V'))
        self.ax2.yaxis.set_major_formatter(FormatStrFormatter('%g A'))
        self.ax3.yaxis.set_major_formatter(FormatStrFormatter('%g mAh'))
        self.ax4.yaxis.set_major_formatter(FormatStrFormatter('%g Wh'))
        
        # Create a combined legend
        lines1, labels1 = self.ax1.get_legend_handles_labels()
        lines2, labels2 = self.ax2.get_legend_handles_labels()
        lines3, labels3 = self.ax3.get_legend_handles_labels()
        lines4, labels4 = self.ax4.get_legend_handles_labels()
        self.ax1.legend(lines1 + lines2 + lines3 + lines4, labels1 + labels2 + labels3 + labels4, loc='best')
        

        
        # Drawing the updated plots
        self.canvas.draw()


    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

root = tk.Tk()
app = App(root)
root.mainloop()
