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

COM_Port = "COM6"


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("DL24 Data Collection and Plotting")
        root.protocol("WM_DELETE_WINDOW", self.on_closing)
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
        
        # Initialize the queue to store data from the data collection thread
        self.data_queue = queue.Queue()
        self.pending_set_actions = []
        time.sleep(0.5)
        self.update_dl24_settings()
        
        # Data collection attributes
        self.csvfile = None
        self.wr = None
        self.collecting_data = False
        self.data_collection_thread = None
        self.last_monotonic = None
        
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
        
        # -- Create empty Line2D objects & store references --
        (self.line_voltage,) = self.ax1.plot([], [], color='green', label='Voltage')
        (self.line_current,) = self.ax2.plot([], [], color='red',   label='Current')
        (self.line_charge,)  = self.ax3.plot([], [], color='blue',  linestyle='--', label='Charge')
        (self.line_energy,)  = self.ax4.plot([], [], color='orange',linestyle='-.', label='Energy')
        
        # Format the axes once
        self.ax1.set_ylabel("Voltage (V)", color='green')
        self.ax2.set_ylabel("Current (A)", color='red')
        self.ax3.set_ylabel("Charge (mAh)", color='blue')
        self.ax4.set_ylabel("Energy (Wh)", color='orange')
        
        # Y-axis format
        self.ax1.yaxis.set_major_formatter(FormatStrFormatter('%g V'))
        self.ax2.yaxis.set_major_formatter(FormatStrFormatter('%g A'))
        self.ax3.yaxis.set_major_formatter(FormatStrFormatter('%g mAh'))
        self.ax4.yaxis.set_major_formatter(FormatStrFormatter('%g Wh'))
        
        # Gather lines from each axes to create combined legend once
        lines1, labels1 = self.ax1.get_legend_handles_labels()
        lines2, labels2 = self.ax2.get_legend_handles_labels()
        lines3, labels3 = self.ax3.get_legend_handles_labels()
        lines4, labels4 = self.ax4.get_legend_handles_labels()
        self.ax1.legend(lines1 + lines2 + lines3 + lines4,
                        labels1 + labels2 + labels3 + labels4,
                        loc='best')
        
        # Force initial draw
        self.canvas.draw()
        

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
        """
        Background thread function: continuously reads *device* voltage/current/
        temp/energy/charge, then puts them into self.data_queue for the main
        thread to (1) do local integration and (2) update plots.
        Also writes device data to the CSV file.
        """
        while self.collecting_data:
            with self.com_port_lock:
                try:
                    with DL24(COM_Port) as dl24:
                        voltage = dl24.get_voltage()
                        current = dl24.get_current()
                        temp = dl24.get_temp()
                        device_energy = dl24.get_energy()   # Device-reported Wh
                        device_charge = dl24.get_charge()   # Device-reported mAh (or Ah, depending on your dl24.py)
                        on_time = dl24.get_time()
    
                        # Timestamp for local logging
                        t = datetime.datetime.now()
    
                        # Simple local power calculation
                        power = voltage * current
    
                        # Enqueue raw data so the main thread can integrate & plot
                        # (t, voltage, current, device_energy, device_charge, temp)
                        self.data_queue.put((t, voltage, current, device_energy, device_charge, temp))
    
                except Exception as e:
                    print(f"Error while collecting data: {e}")
                    # Maybe wait a bit longer so it doesn't spam at 0.5 s
                    time.sleep(2.0)
                    continue
    
            # -----------------
            # CSV writing logic
            # -----------------
            out_path = self.output_var.get()
            if out_path:
                exists = os.path.exists(out_path)
                if self.csvfile is None:
                    if self.append_var.get() and exists:
                        self.csvfile = open(out_path, 'a', newline='')
                    else:
                        self.csvfile = open(out_path, 'w', newline='')
                    self.wr = csv.writer(self.csvfile)
                    # CSV header: renamed columns to reflect these are device counters
                    self.wr.writerow([
                        'date', 'voltage', 'current', 'Power',
                        'device_energy', 'device_charge', 'temp',
                        'time_seconds', 'time_str'
                    ])
    
                if self.wr:
                    days = on_time.days
                    seconds = on_time.seconds
                    hours = seconds // 3600
                    minutes = (seconds // 60) % 60
                    seconds = seconds % 60
                    time_sec = int(on_time.total_seconds())
                    time_str = f"{days:01d}d. {hours:02d}:{minutes:02d}:{seconds:02d}"
    
                    data = [
                        t.strftime("%Y-%m-%d %H:%M:%S"),
                        f"{voltage:.3f}",
                        f"{current:.3f}",
                        f"{power:.2f}",
                        f"{device_energy:.3f}",   # device-reported Wh
                        f"{device_charge:.1f}",   # device-reported mAh
                        f"{temp:.0f}",
                        f"{time_sec}",
                        time_str,
                    ]
                    self.wr.writerow(data)
                    self.csvfile.flush()
    
            # Sleep for ~0.5 s between reads
            time.sleep(0.5)
    
    
    def check_data_queue(self):
        """
        Pulls all available data from self.data_queue, updates local time-series
        arrays (date_series, voltage_series, current_series, etc.), computes local
        integrated charge/energy (after the first sample), and compares them to
        the device counters. Prints a warning if difference exceeds 1%.
        """
    
        # First, handle any pending "set" actions
        for action in self.pending_set_actions:
            action()
        self.pending_set_actions.clear()
    
        try:
            # Drain the queue of all data points that arrived since last call
            while True:
                # The background thread enqueues: (t, V, I, devEnergy, devCharge, temp)
                t, voltage, current, device_energy, device_charge, temp = self.data_queue.get_nowait()
    
                # Local power calculation
                power = voltage * current
    
                if len(self.date_series) == 0:
                    #
                    # -- FIRST DATA POINT: Use device counters directly --
                    #
                    self.date_series.append(t)
                    self.voltage_series.append(voltage)
                    self.current_series.append(current)
    
                    # Start the local arrays from device’s reported counters:
                    self.energy_series.append(device_energy)   # Wh
                    self.charge_series.append(device_charge)   # mAh
                else:
                    #
                    # -- SUBSEQUENT DATA POINTS: local integration from prior local values --
                    #
                    now_monotonic = time.monotonic()
                    if self.last_monotonic is None:
                        # First data point: no previous time
                        dt = 0.0
                    else:
                        dt = now_monotonic - self.last_monotonic
                    self.last_monotonic = now_monotonic
                    
                    
                    self.date_series.append(t)
                    self.voltage_series.append(voltage)
                    self.current_series.append(current)
    
                    # Local integrated totals
                    local_charge = self.charge_series[-1] + (current * dt) / 3.6
                    local_energy = self.energy_series[-1] + (power * dt) / 3600.0
    
                    self.charge_series.append(local_charge)
                    self.energy_series.append(local_energy)
    
                    #
                    # -- Compare local vs. device counters -> warn if >1% difference --
                    #
                    # If device_charge is in mAh, we compare directly
                    if device_charge > 0.01:
                        err_charge_pct = abs(local_charge - device_charge) / device_charge * 100.0
                        if err_charge_pct > 1.0:
                            print(
                                f"Warning: local charge differs from device by {err_charge_pct:.2f}% "
                                f"(local={local_charge:.1f} mAh, device={device_charge:.1f} mAh)"
                            )
    
                    if device_energy > 0.0001:
                        err_energy_pct = abs(local_energy - device_energy) / device_energy * 100.0
                        if err_energy_pct > 1.0:
                            print(
                                f"Warning: local energy differs from device by {err_energy_pct:.2f}% "
                                f"(local={local_energy:.3f} Wh, device={device_energy:.3f} Wh)"
                            )
    
                #
                # -- Print data line to console (show local integrated totals) --
                #
                time_str = t.strftime("%Y.%m.%d %H:%M:%S.%f")[:-4]  # discard last digits of microseconds
                data_str = (
                    f"{time_str} | {voltage:6.03f} V | {current:6.3f} A "
                    f"| {power:6.2f} W | {self.energy_series[-1]:6.3f} Wh "
                    f"| {self.charge_series[-1]:7.1f} mAh | {temp:4.1f} °C"
                )
                print(data_str)
    
        except queue.Empty:
            # No more items in the queue
            pass
        
        self.update_plot()
        # Reschedule check_data_queue if still collecting data
        if self.collecting_data:
            self.root.after(400, self.check_data_queue)
    
        
    
    
    
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
            self.last_monotonic = None
    
            # Update the plot
            self.update_plot()
    
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
            

            
                
    def update_plot(self):
        """
        Update the data in the existing line objects without clearing axes.
        Then refresh the figure.
        """
        # 1) Update each line's data
        self.line_voltage.set_xdata(self.date_series)
        self.line_voltage.set_ydata(self.voltage_series)
        
        self.line_current.set_xdata(self.date_series)
        self.line_current.set_ydata(self.current_series)

        self.line_charge.set_xdata(self.date_series)
        self.line_charge.set_ydata(self.charge_series)

        self.line_energy.set_xdata(self.date_series)
        self.line_energy.set_ydata(self.energy_series)

        # 2) Update the axis limits so new data points are visible
        self.ax1.relim()  # Recalculate limits for ax1
        self.ax1.autoscale_view()

        self.ax2.relim()
        self.ax2.autoscale_view()

        self.ax3.relim()
        self.ax3.autoscale_view()

        self.ax4.relim()
        self.ax4.autoscale_view()

        # 3) Finally, redraw the figure
        self.canvas.draw_idle()



    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def on_closing(self):
        if self.collecting_data:
            self.stop_data_collection()
        self.root.destroy()

root = tk.Tk()
app = App(root)
root.mainloop()

