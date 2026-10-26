from __future__ import annotations

import csv
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .analysis import METRICS, analyze, build_baseline, overall_risk
from .chart import CORAL, TEAL, TrendChart
from .datasets import build_catalog
from .device import Device, is_log, likely_port
from .references import tailored_cap_comparison
from .storage import Store

EVERGREEN="#123B36"; EVERGREEN_2="#0C2D29"; CANVAS="#F3F7F5"; WHITE="#FFFFFF"
INK="#17332F"; MUTED="#6E817D"; LINE="#DCE8E4"; MINT="#DDF4ED"; MINT_2="#EFF9F5"
AMBER="#E6A23C"; AMBER_BG="#FFF5DF"; RED="#D85C5C"; RED_BG="#FDEAEA"; BLUE="#3B7C89"


def resource_path(relative):
    base=Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parents[1]))
    return base/relative


class MoldSenseApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MoldSense · Environmental insights")
        self.geometry("1320x820"); self.minsize(1080,700); self.configure(bg=CANVAS)
        self.store=Store(); self.device=None; self.port=None; self.busy=False
        self.rows=[]; self.deviations=[]; self.catalog=[]; self.dataset_by_name={}; self.cap_comparison=tailored_cap_comparison()
        self._load_icon(); self._style(); self._shell(); self.refresh_data(); self.show_view("overview")
        self.protocol("WM_DELETE_WINDOW",self.close_app); self.after(600,self.detect_device)

    def _load_icon(self):
        try:
            self.icon_image=tk.PhotoImage(file=resource_path("assets/moldsense-icon.png")); self.iconphoto(True,self.icon_image)
        except tk.TclError:self.icon_image=None

    def _style(self):
        style=ttk.Style(self); style.theme_use("clam")
        style.configure("TCombobox",fieldbackground=WHITE,background=WHITE,foreground=INK,arrowcolor=EVERGREEN,padding=8,font=("Segoe UI",10))
        style.map("TCombobox",fieldbackground=[("readonly",WHITE)],selectbackground=[("readonly",WHITE)],selectforeground=[("readonly",INK)])
        style.configure("TCheckbutton",background=WHITE,foreground=INK,font=("Segoe UI",10)); style.map("TCheckbutton",background=[("active",WHITE)])
        style.configure("Treeview",background=WHITE,fieldbackground=WHITE,foreground=INK,rowheight=34,borderwidth=0,font=("Segoe UI",9))
        style.configure("Treeview.Heading",background="#EAF2EF",foreground=EVERGREEN,borderwidth=0,font=("Segoe UI Semibold",9),padding=(8,9))
        style.map("Treeview",background=[("selected",MINT)],foreground=[("selected",EVERGREEN)])

    def _shell(self):
        self.sidebar=tk.Frame(self,bg=EVERGREEN_2,width=218); self.sidebar.pack(side="left",fill="y"); self.sidebar.pack_propagate(False)
        brand=tk.Frame(self.sidebar,bg=EVERGREEN_2,height=112); brand.pack(fill="x"); brand.pack_propagate(False)
        tk.Label(brand,text="M",font=("Segoe UI Semibold",20),bg=TEAL,fg=WHITE,width=2,height=1).pack(side="left",padx=(20,12),pady=28)
        brand_text=tk.Frame(brand,bg=EVERGREEN_2); brand_text.pack(side="left",pady=27)
        tk.Label(brand_text,text="MoldSense",font=("Segoe UI Semibold",17),bg=EVERGREEN_2,fg=WHITE).pack(anchor="w")
        tk.Label(brand_text,text="MOLD DETECTION SYSTEM",font=("Segoe UI Semibold",8),bg=EVERGREEN_2,fg="#7FC5B7").pack(anchor="w")
        tk.Label(self.sidebar,text="WORKSPACE",font=("Segoe UI Semibold",8),bg=EVERGREEN_2,fg="#72958F").pack(anchor="w",padx=22,pady=(8,8))
        self.nav_buttons={}
        for key,label,glyph in (("overview","Overview","⌂"),("explore","Explore data","⌁"),("deviations","Deviations","!"),("data","Data library","▤"),("about","Help & safety","?")):
            button=tk.Button(self.sidebar,text=f" {glyph}   {label}",anchor="w",font=("Segoe UI Semibold",10),bg=EVERGREEN_2,fg="#C9DDD8",activebackground="#174B44",activeforeground=WHITE,relief="flat",bd=0,padx=18,pady=12,command=lambda k=key:self.show_view(k))
            button.pack(fill="x",padx=8,pady=2); self.nav_buttons[key]=button
        bottom=tk.Frame(self.sidebar,bg="#0A2623"); bottom.pack(side="bottom",fill="x",padx=12,pady=12)
        self.side_device_dot=tk.Label(bottom,text="●",font=("Segoe UI",12),bg="#0A2623",fg="#78928E"); self.side_device_dot.pack(side="left",padx=(10,7),pady=11)
        self.side_device=tk.Label(bottom,text="Device not connected",font=("Segoe UI",9),bg="#0A2623",fg="#B8CECA"); self.side_device.pack(side="left",pady=11)

        self.main=tk.Frame(self,bg=CANVAS); self.main.pack(side="left",fill="both",expand=True)
        top=tk.Frame(self.main,bg=WHITE,height=76,highlightbackground=LINE,highlightthickness=1); top.pack(fill="x"); top.pack_propagate(False)
        self.page_title=tk.Label(top,text="Overview",font=("Segoe UI Semibold",20),bg=WHITE,fg=INK); self.page_title.pack(side="left",padx=28)
        self.import_button=self._button(top,"Import from device",self.import_clear,accent=True); self.import_button.pack(side="right",padx=(10,24),pady=17)
        self.connection=tk.Label(top,text="●  Plug in MoldSense",font=("Segoe UI Semibold",9),bg=MINT_2,fg=MUTED,padx=13,pady=8); self.connection.pack(side="right",pady=20)
        self.view_host=tk.Frame(self.main,bg=CANVAS); self.view_host.pack(fill="both",expand=True)
        self.views={}; self._overview_view(); self._explore_view(); self._deviation_view(); self._data_view(); self._about_view()
        self.status_var=tk.StringVar(value="Ready"); tk.Label(self.main,textvariable=self.status_var,bg="#E8F0ED",fg=MUTED,anchor="w",font=("Segoe UI",8),padx=14,pady=4).pack(side="bottom",fill="x")

    def _button(self,parent,text,command,accent=False,small=False):
        return tk.Button(parent,text=text,command=command,font=("Segoe UI Semibold",9 if small else 10),bg=TEAL if accent else WHITE,fg=WHITE if accent else EVERGREEN,activebackground="#0C7566" if accent else MINT,activeforeground=WHITE if accent else EVERGREEN,relief="flat",bd=0,padx=13 if small else 17,pady=7 if small else 9,highlightbackground=LINE,highlightthickness=1,cursor="hand2")

    def _card(self,parent,padx=18,pady=16):return tk.Frame(parent,bg=WHITE,highlightbackground=LINE,highlightthickness=1,padx=padx,pady=pady)
    def _screen(self,key):
        frame=tk.Frame(self.view_host,bg=CANVAS); self.views[key]=frame; return frame

    def _overview_view(self):
        view=self._screen("overview"); body=tk.Frame(view,bg=CANVAS); body.pack(fill="both",expand=True,padx=26,pady=22)
        welcome=tk.Frame(body,bg=CANVAS); welcome.pack(fill="x"); left=tk.Frame(welcome,bg=CANVAS); left.pack(side="left")
        tk.Label(left,text="Your environment at a glance",font=("Segoe UI Semibold",22),bg=CANVAS,fg=INK).pack(anchor="w")
        tk.Label(left,text="Review sensor history, compare tests, and understand meaningful changes.",font=("Segoe UI",10),bg=CANVAS,fg=MUTED).pack(anchor="w",pady=(3,0))
        self._button(welcome,"Open data explorer",lambda:self.show_view("explore"),accent=True,small=True).pack(side="right",pady=8)
        self.risk_card=self._card(body,padx=20,pady=17); self.risk_card.pack(fill="x",pady=(18,14))
        self.risk_badge=tk.Label(self.risk_card,text="NO BASELINE",font=("Segoe UI Semibold",9),bg=AMBER_BG,fg="#9A6816",padx=10,pady=5); self.risk_badge.pack(side="left")
        risk_copy=tk.Frame(self.risk_card,bg=WHITE); risk_copy.pack(side="left",fill="x",expand=True,padx=16)
        self.risk_heading=tk.Label(risk_copy,text="Establish a room baseline",font=("Segoe UI Semibold",14),bg=WHITE,fg=INK); self.risk_heading.pack(anchor="w")
        self.risk_text=tk.Label(risk_copy,text="Import ordinary room readings before assessing change.",font=("Segoe UI",9),bg=WHITE,fg=MUTED,wraplength=760,justify="left"); self.risk_text.pack(anchor="w",pady=(3,0))
        self._button(self.risk_card,"Set baseline",self.save_baseline,small=True).pack(side="right")
        stats=tk.Frame(body,bg=CANVAS); stats.pack(fill="x"); self.stat_values={}
        for index,(key,label,color) in enumerate((("readings","Saved readings",TEAL),("datasets","Available datasets",BLUE),("deviations","Deviation periods",CORAL),("baseline","Baseline signals",AMBER))):
            card=self._card(stats,padx=16,pady=12); card.grid(row=0,column=index,sticky="nsew",padx=(0 if index==0 else 6,0 if index==3 else 6)); stats.grid_columnconfigure(index,weight=1)
            tk.Frame(card,bg=color,width=4,height=42).pack(side="left",padx=(0,12)); value=tk.Label(card,text="0",font=("Segoe UI Semibold",21),bg=WHITE,fg=INK); value.pack(anchor="w"); tk.Label(card,text=label,font=("Segoe UI",9),bg=WHITE,fg=MUTED).pack(anchor="w"); self.stat_values[key]=value
        lower=tk.Frame(body,bg=CANVAS); lower.pack(fill="both",expand=True,pady=(14,0)); lower.grid_columnconfigure(0,weight=3); lower.grid_columnconfigure(1,weight=2); lower.grid_rowconfigure(0,weight=1)
        recent=self._card(lower); recent.grid(row=0,column=0,sticky="nsew",padx=(0,7)); tk.Label(recent,text="Recent datasets",font=("Segoe UI Semibold",13),bg=WHITE,fg=INK).pack(anchor="w"); tk.Label(recent,text="Previous tests and local references ready to compare",font=("Segoe UI",9),bg=WHITE,fg=MUTED).pack(anchor="w",pady=(2,10))
        self.recent_tree=ttk.Treeview(recent,columns=("name","type","rows"),show="headings",height=6); self.recent_tree.heading("name",text="Dataset"); self.recent_tree.heading("type",text="Type"); self.recent_tree.heading("rows",text="Readings"); self.recent_tree.column("name",width=300); self.recent_tree.column("type",width=120); self.recent_tree.column("rows",width=75,anchor="e"); self.recent_tree.pack(fill="both",expand=True); self.recent_tree.bind("<Double-1>",self._recent_open)
        comparison=self._card(lower); comparison.grid(row=0,column=1,sticky="nsew",padx=(7,0)); tk.Label(comparison,text="Reference comparison",font=("Segoe UI Semibold",13),bg=WHITE,fg=INK).pack(anchor="w"); tk.Label(comparison,text="Tailored Cap 1 vs Cap 2",font=("Segoe UI",9),bg=WHITE,fg=MUTED).pack(anchor="w",pady=(2,13))
        self.compare_value=tk.Label(comparison,text="Not available",font=("Segoe UI Semibold",30),bg=WHITE,fg=TEAL); self.compare_value.pack(anchor="w"); tk.Label(comparison,text="mean gas-profile separation",font=("Segoe UI",9),bg=WHITE,fg=MUTED).pack(anchor="w")
        self.compare_environment=tk.Label(comparison,text="",font=("Segoe UI",9),bg=MINT_2,fg=EVERGREEN,justify="left",padx=12,pady=10); self.compare_environment.pack(fill="x",pady=14); self._button(comparison,"View overlaid graph",self._open_reference_overlay,small=True).pack(anchor="w")

    def _explore_view(self):
        view=self._screen("explore"); body=tk.Frame(view,bg=CANVAS); body.pack(fill="both",expand=True,padx=26,pady=20)
        tk.Label(body,text="Compare your readings",font=("Segoe UI Semibold",21),bg=CANVAS,fg=INK).pack(anchor="w"); tk.Label(body,text="Choose any previous test or reference, overlay a second dataset, and inspect values by hovering.",font=("Segoe UI",10),bg=CANVAS,fg=MUTED).pack(anchor="w",pady=(2,10))
        controls=self._card(body,padx=14,pady=12); controls.pack(fill="x"); controls.grid_columnconfigure(0,weight=1); controls.grid_columnconfigure(1,weight=1)
        for column,text in enumerate(("PRIMARY DATASET","COMPARE WITH","SIGNAL")):tk.Label(controls,text=text,font=("Segoe UI Semibold",8),bg=WHITE,fg=MUTED).grid(row=0,column=column,sticky="w",padx=(10 if column else 0,0))
        self.primary_var=tk.StringVar(); self.compare_var=tk.StringVar(); self.metric_var=tk.StringVar(value="Gas resistance")
        self.primary_box=ttk.Combobox(controls,textvariable=self.primary_var,state="readonly",width=31); self.primary_box.grid(row=1,column=0,sticky="ew",pady=(4,0)); self.primary_box.bind("<<ComboboxSelected>>",lambda _e:self.update_chart())
        self.compare_box=ttk.Combobox(controls,textvariable=self.compare_var,state="readonly",width=31); self.compare_box.grid(row=1,column=1,sticky="ew",padx=(10,0),pady=(4,0)); self.compare_box.bind("<<ComboboxSelected>>",lambda _e:self.update_chart())
        self.metric_box=ttk.Combobox(controls,textvariable=self.metric_var,state="readonly",values=[label for label,_unit in METRICS.values()],width=17); self.metric_box.grid(row=1,column=2,padx=(10,0),pady=(4,0)); self.metric_box.bind("<<ComboboxSelected>>",lambda _e:self.update_chart())
        self.overlay_var=tk.BooleanVar(value=True); self.means_var=tk.BooleanVar(value=False); ttk.Checkbutton(controls,text="Overlay",variable=self.overlay_var,command=self.update_chart).grid(row=1,column=3,padx=(14,0)); ttk.Checkbutton(controls,text="Mean lines",variable=self.means_var,command=self.update_chart).grid(row=1,column=4,padx=(8,0))
        self._button(controls,"Use as baseline",self.set_primary_baseline,small=True).grid(row=1,column=5,padx=(10,0)); self._button(controls,"Export",self.export_primary,accent=True,small=True).grid(row=1,column=6,padx=(8,0))
        summary=tk.Frame(body,bg=CANVAS); summary.pack(fill="x",pady=(10,8)); self.chart_summary=tk.Label(summary,text="",font=("Segoe UI Semibold",9),bg=CANVAS,fg=EVERGREEN); self.chart_summary.pack(side="left"); tk.Label(summary,text="Gas resistance uses a logarithmic scale so every heater step remains visible.",font=("Segoe UI",8),bg=CANVAS,fg=MUTED).pack(side="right")
        chart_card=self._card(body,padx=10,pady=8); chart_card.pack(fill="both",expand=True); self.chart=TrendChart(chart_card); self.chart.pack(fill="both",expand=True)

    def _deviation_view(self):
        view=self._screen("deviations"); body=tk.Frame(view,bg=CANVAS); body.pack(fill="both",expand=True,padx=26,pady=20)
        tk.Label(body,text="Deviation review",font=("Segoe UI Semibold",21),bg=CANVAS,fg=INK).pack(anchor="w"); tk.Label(body,text="Marked periods are evidence of environmental change—not a diagnosis or proof of mold.",font=("Segoe UI",10),bg=CANVAS,fg=MUTED).pack(anchor="w",pady=(2,12))
        filters=self._card(body,padx=13,pady=10); filters.pack(fill="x"); tk.Label(filters,text="Show",font=("Segoe UI Semibold",9),bg=WHITE,fg=INK).pack(side="left"); self.severity_var=tk.StringVar(value="All findings"); severity=ttk.Combobox(filters,textvariable=self.severity_var,state="readonly",values=("All findings","High","Moderate","Reference"),width=18); severity.pack(side="left",padx=10); severity.bind("<<ComboboxSelected>>",lambda _e:self.populate_deviations()); self.deviation_count=tk.Label(filters,text="",bg=WHITE,fg=MUTED,font=("Segoe UI",9)); self.deviation_count.pack(side="right")
        card=self._card(body,padx=0,pady=0); card.pack(fill="both",expand=True,pady=(10,0)); cols=("severity","period","signal","difference","guidance"); self.event_tree=ttk.Treeview(card,columns=cols,show="headings")
        for col,width in zip(cols,(90,220,125,290,440)):self.event_tree.heading(col,text=col.title()); self.event_tree.column(col,width=width,anchor="w")
        self.event_tree.pack(fill="both",expand=True); self.event_tree.bind("<<TreeviewSelect>>",self._deviation_detail)
        self.deviation_detail=tk.Label(body,text="Select a finding to read the full interpretation.",font=("Segoe UI",9),bg=MINT_2,fg=EVERGREEN,anchor="w",justify="left",wraplength=1000,padx=14,pady=10); self.deviation_detail.pack(fill="x",pady=(8,0))

    def _data_view(self):
        view=self._screen("data"); body=tk.Frame(view,bg=CANVAS); body.pack(fill="both",expand=True,padx=26,pady=20)
        heading=tk.Frame(body,bg=CANVAS); heading.pack(fill="x"); left=tk.Frame(heading,bg=CANVAS); left.pack(side="left"); tk.Label(left,text="Data library",font=("Segoe UI Semibold",21),bg=CANVAS,fg=INK).pack(anchor="w"); tk.Label(left,text="Your imported tests and checksum-protected references in one place.",font=("Segoe UI",10),bg=CANVAS,fg=MUTED).pack(anchor="w",pady=(2,0)); self._button(heading,"Open archive folder",self.open_logs,small=True).pack(side="right",pady=6); self._button(heading,"Add files",self.import_files,accent=True,small=True).pack(side="right",padx=8,pady=6)
        tools=self._card(body,padx=12,pady=9); tools.pack(fill="x",pady=(14,10)); tk.Label(tools,text="Search",bg=WHITE,fg=MUTED,font=("Segoe UI",9)).pack(side="left"); self.search_var=tk.StringVar(); entry=tk.Entry(tools,textvariable=self.search_var,bg="#F7FAF9",fg=INK,relief="flat",font=("Segoe UI",10),width=34); entry.pack(side="left",padx=10,ipady=6); entry.bind("<KeyRelease>",lambda _e:self.populate_library()); self._button(tools,"Compare selected",self.compare_selected,accent=True,small=True).pack(side="right"); self._button(tools,"Export selected",self.export_selected,small=True).pack(side="right",padx=8)
        card=self._card(body,padx=0,pady=0); card.pack(fill="both",expand=True); cols=("name","kind","mode","readings","created","integrity"); self.library_tree=ttk.Treeview(card,columns=cols,show="headings")
        for col,width in zip(cols,(330,145,120,90,145,165)):self.library_tree.heading(col,text=col.title()); self.library_tree.column(col,width=width,anchor="e" if col=="readings" else "w")
        self.library_tree.pack(fill="both",expand=True); self.library_tree.bind("<Double-1>",lambda _e:self.compare_selected()); self.library_detail=tk.Label(body,text="Select a dataset for details.",font=("Segoe UI",9),bg=MINT_2,fg=EVERGREEN,anchor="w",padx=14,pady=9); self.library_detail.pack(fill="x",pady=(8,0)); self.library_tree.bind("<<TreeviewSelect>>",self._library_detail)

    def _about_view(self):
        view=self._screen("about"); body=tk.Frame(view,bg=CANVAS); body.pack(fill="both",expand=True,padx=26,pady=22)
        tk.Label(body,text="Help & safety",font=("Segoe UI Semibold",21),bg=CANVAS,fg=INK).pack(anchor="w"); tk.Label(body,text="A straightforward guide for reliable measurements and responsible interpretation.",font=("Segoe UI",10),bg=CANVAS,fg=MUTED).pack(anchor="w",pady=(2,14))
        grid=tk.Frame(body,bg=CANVAS); grid.pack(fill="both",expand=True); grid.grid_columnconfigure(0,weight=1); grid.grid_columnconfigure(1,weight=1)
        sections=(("Using MoldSense","1. Collect readings with the physical buttons on the device.\n2. Plug it in and import the logs.\n3. Establish a baseline from ordinary room conditions.\n4. Compare later tests and review marked deviations."),("How imports stay safe","Each recognized log is downloaded twice and must match byte-for-byte. A SHA-256 manifest is saved before deletion is requested. BSEC state and model files are never eligible for deletion."),("What a warning means","A warning means the environment changed relative to your baseline. Check moisture, ventilation, odors, cleaning products, occupancy, temperature, and sensor placement. Repeat unclear tests under similar conditions."),("Important limitation","MoldSense cannot prove mold is present, identify a species or chemical, determine medical safety, or replace inspection and professional testing. Low IAQ accuracy reduces confidence."))
        for i,(title,text) in enumerate(sections):
            card=self._card(grid,padx=20,pady=18); card.grid(row=i//2,column=i%2,sticky="nsew",padx=(0 if i%2==0 else 7,0 if i%2 else 7),pady=(0 if i<2 else 7,7 if i<2 else 0)); grid.grid_rowconfigure(i//2,weight=1); tk.Label(card,text=title,font=("Segoe UI Semibold",14),bg=WHITE,fg=INK).pack(anchor="w"); tk.Label(card,text=text,font=("Segoe UI",10),bg=WHITE,fg=MUTED,justify="left",wraplength=430).pack(anchor="w",pady=(9,0))
        footer=tk.Frame(body,bg=CANVAS); footer.pack(fill="x",pady=(14,0)); tk.Label(footer,text=f"Local data: {self.store.root}",font=("Segoe UI",8),bg=CANVAS,fg=MUTED).pack(side="left"); tk.Label(footer,text="MoldSense User Dashboard · Version 1.1",font=("Segoe UI Semibold",8),bg=CANVAS,fg=MUTED).pack(side="right")

    def show_view(self,key):
        titles={"overview":"Overview","explore":"Explore data","deviations":"Deviations","data":"Data library","about":"Help & safety"}
        for frame in self.views.values():frame.pack_forget()
        self.views[key].pack(fill="both",expand=True); self.page_title.configure(text=titles[key])
        for name,button in self.nav_buttons.items():button.configure(bg="#174B44" if name==key else EVERGREEN_2,fg=WHITE if name==key else "#C9DDD8")

    def status(self,text):self.status_var.set(text)
    def work(self,fn):
        if self.busy:return
        self.busy=True; self.import_button.configure(state="disabled"); self.status("Working…")
        def run():
            try:fn()
            except Exception as exc:self.after(0,lambda e=exc:messagebox.showerror("MoldSense",str(e)))
            finally:self.after(0,self._work_done)
        threading.Thread(target=run,daemon=True).start()
    def _work_done(self):self.busy=False; self.import_button.configure(state="normal"); self.status("Ready")

    def detect_device(self):
        if not self.busy:
            found=likely_port()
            if found!=self.port:
                if self.device:
                    try:self.device.close()
                    except Exception:pass
                self.device=None; self.port=found
                if found:self._device_state(f"Checking {found}",AMBER); threading.Thread(target=self._connect,daemon=True).start()
                else:self._device_state("Plug in MoldSense",MUTED)
        self.after(2500,self.detect_device)
    def _connect(self):
        try:
            dev=Device(self.port); dev.identify(); self.device=dev; self.after(0,lambda:self._device_state(f"Connected · {self.port}",TEAL))
        except Exception:self.port=None; self.after(0,lambda:self._device_state("Device unavailable",RED))
    def _device_state(self,text,color):self.connection.configure(text=f"●  {text}",fg=color); self.side_device.configure(text=text); self.side_device_dot.configure(fg=color)
    def require_device(self):
        if not self.device:raise RuntimeError("Plug in the MoldSense device and wait for the green Connected status.")
        return self.device

    def import_clear(self):
        def task():
            dev=self.require_device(); files=[item for item in dev.list_files() if is_log(item[0]) and item[1]>0]
            if not files:raise RuntimeError("No device logs are ready to import.")
            imported=[]; warning=None; can_delete=True
            for index,(name,size) in enumerate(files,1):
                self.after(0,lambda n=name,i=index,t=len(files):self.status(f"Verifying {i} of {t} · {n}")); first=dev.download(name); second=dev.download(name)
                if len(first)!=size or first!=second:raise RuntimeError(f"Verification failed for {name}. Nothing was deleted.")
                _path,digest=self.store.archive(name,first,dev.port); imported.append(f"{name}  •  {digest[:10]}…")
                if can_delete:
                    try:dev.delete_log(name)
                    except RuntimeError as exc:warning=str(exc); can_delete=False
            self.after(0,self.refresh_data); text=f"Imported and verified {len(imported)} file(s).\n\n"+"\n".join(imported)
            if warning:text+=f"\n\nDevice storage was not cleared:\n{warning}"
            self.after(0,lambda:messagebox.showwarning("Import complete",text) if warning else messagebox.showinfo("Import complete",text))
        self.work(task)

    def refresh_data(self):
        self.rows=self.store.csv_rows(); baseline=self.store.get_json("baseline",{}); self.deviations=analyze(self.rows,baseline) if baseline else []; self.catalog=build_catalog(self.store); self.dataset_by_name={item.name:item for item in self.catalog}
        self._refresh_overview(baseline); self._refresh_dataset_boxes(); self.populate_deviations(); self.populate_library(); self.update_chart()

    def _refresh_overview(self,baseline):
        risk,copy=overall_risk(self.deviations)
        if not baseline:risk,copy="NO BASELINE","Import readings from ordinary room conditions, then establish your reference."
        style={"NORMAL":("NORMAL",MINT,TEAL,"No significant change detected"),"WATCH":("WATCH",AMBER_BG,"#9A6816","Review the marked periods"),"HIGH":("HIGH",RED_BG,RED,"A strong environmental change was detected"),"NO BASELINE":("NO BASELINE",AMBER_BG,"#9A6816","Establish a room baseline")}[risk]
        self.risk_badge.configure(text=style[0],bg=style[1],fg=style[2]); self.risk_heading.configure(text=style[3]); self.risk_text.configure(text=copy)
        for key,value in (("readings",len(self.rows)),("datasets",len(self.catalog)),("deviations",len(self.deviations)),("baseline",len(baseline))):self.stat_values[key].configure(text=str(value))
        self.recent_tree.delete(*self.recent_tree.get_children())
        for item in self.catalog[:7]:self.recent_tree.insert("","end",iid=item.key,values=(item.name,item.kind,f"{item.readings:,}"))
        cap=self.cap_comparison
        if cap is None:
            self.compare_value.configure(text="Not available")
            self.compare_environment.configure(text="Add your local reference captures to enable comparison.")
        else:
            self.compare_value.configure(text=f"{cap['gas_deviation']:.2f}%")
            self.compare_environment.configure(text=f"Temperature  {cap['temperature_delta']:+.2f} °C\nHumidity       {cap['humidity_delta']:+.2f}% RH\nPressure       {cap['pressure_delta']:+.2f} hPa")

    def _refresh_dataset_boxes(self):
        names=[item.name for item in self.catalog]; current_a=self.primary_var.get(); current_b=self.compare_var.get(); self.primary_box.configure(values=names); self.compare_box.configure(values=names)
        if current_a not in names:self.primary_var.set(next((name for name in names if "Tailored" in name),names[0] if names else ""))
        if current_b not in names:self.compare_var.set(next((name for name in names if "Cap 2 ·" in name),names[1] if len(names)>1 else (names[0] if names else "")))
    def _metric_key(self):return next((key for key,(label,_unit) in METRICS.items() if label==self.metric_var.get()),"gas_ohms")
    def update_chart(self):
        if not hasattr(self,"chart"):return
        primary=self.dataset_by_name.get(self.primary_var.get()); comparison=self.dataset_by_name.get(self.compare_var.get()) if self.overlay_var.get() else None; metric=self._metric_key()
        if primary and not primary.supports(metric):
            available=primary.metrics()
            if available:metric=available[0]; self.metric_var.set(METRICS[metric][0])
        rows_a=primary.rows if primary else []; rows_b=comparison.rows if comparison and comparison.supports(metric) else []; labels=(self._short_name(primary),self._short_name(comparison)); self.chart.set_data(rows_a,metric,rows_b,labels,self.means_var.get())
        if primary:self.chart_summary.configure(text=f"{primary.readings:,} primary readings"+(f"  ·  {comparison.readings:,} comparison readings" if rows_b else ""))
    def _short_name(self,item):return item.name.split(" · ")[0] if item else "Comparison"

    def save_baseline(self):
        candidates=[row for row in self.rows if str(row.get("mode","")).upper() in ("INITIALIZE","BASELINE")]; self._set_baseline(candidates or self.rows,"saved environmental readings")
    def set_primary_baseline(self):
        item=self.dataset_by_name.get(self.primary_var.get())
        if item:self._set_baseline(item.rows,item.name)
    def _set_baseline(self,rows,label):
        baseline=build_baseline(rows)
        if not baseline:messagebox.showwarning("Baseline unavailable","This dataset does not contain at least five recognized environmental readings.");return
        if messagebox.askyesno("Establish baseline",f"Use {len(rows):,} readings from “{label}” as the normal room reference?\n\nThis changes only local analysis; it never initializes or retrains the device."):
            self.store.set_json("baseline",baseline); self.refresh_data(); self.show_view("overview")

    def _reference_findings(self):
        if self.cap_comparison is None:
            return []
        cap=self.cap_comparison; rows=[("Reference","Tailored Cap 1 — Cap 2","Gas profile",f"{cap['gas_deviation']:.2f}% mean symmetric deviation across 10 heater steps","Separation between captures; not proof of mold, identity, or safety.")]
        rows.extend(("Reference",f"Heater step {item['step']}","Gas resistance",f"{item['deviation']:.2f}% · {item['cap_1']:.0f} Ω vs {item['cap_2']:.0f} Ω","Review as part of the complete profile, not as a standalone diagnosis.") for item in cap["steps"]); return rows
    def populate_deviations(self):
        if not hasattr(self,"event_tree"):return
        rows=[(item.severity,f"{item.start} — {item.end}",METRICS[item.metric][0],item.explanation,item.risk) for item in self.deviations]+self._reference_findings(); selected=self.severity_var.get(); rows=[row for row in rows if selected=="All findings" or row[0]==selected]
        self.event_tree.delete(*self.event_tree.get_children()); [self.event_tree.insert("","end",values=row) for row in rows]; self.deviation_count.configure(text=f"{len(rows)} finding(s)")
    def _deviation_detail(self,_event=None):
        selection=self.event_tree.selection()
        if selection:
            values=self.event_tree.item(selection[0],"values"); self.deviation_detail.configure(text=f"{values[1]} · {values[2]}\n{values[3]}  {values[4]}")

    def populate_library(self):
        if not hasattr(self,"library_tree"):return
        query=self.search_var.get().strip().lower(); self.library_tree.delete(*self.library_tree.get_children())
        for item in self.catalog:
            if query and query not in f"{item.name} {item.kind} {item.mode}".lower():continue
            integrity=(item.sha256[:12]+"…") if item.sha256 else "Local database"; self.library_tree.insert("","end",iid=item.key,values=(item.name,item.kind,item.mode,f"{item.readings:,}",item.created,integrity))
    def _selected_dataset(self):
        selection=self.library_tree.selection(); return next((item for item in self.catalog if selection and item.key==selection[0]),None)
    def _library_detail(self,_event=None):
        item=self._selected_dataset()
        if item:self.library_detail.configure(text=f"{item.name}  ·  {item.readings:,} readings  ·  {item.size:,} bytes  ·  {item.path or 'Local combined view'}")
    def compare_selected(self):
        item=self._selected_dataset()
        if item:self.primary_var.set(item.name); self.show_view("explore"); self.update_chart()
    def export_selected(self):
        item=self._selected_dataset()
        if item:self._export_dataset(item)
    def export_primary(self):
        item=self.dataset_by_name.get(self.primary_var.get())
        if item:self._export_dataset(item)
    def _export_dataset(self,item):
        path=filedialog.asksaveasfilename(title="Export dataset",defaultextension=".csv",filetypes=(("CSV file","*.csv"),),initialfile=item.name.replace(" · ","_").replace(" ","_")+".csv")
        if not path:return
        keys=[]
        for row in item.rows:
            for key in row:
                if key not in keys and not key.startswith("_"):keys.append(key)
        with open(path,"w",encoding="utf-8",newline="") as handle:
            writer=csv.DictWriter(handle,fieldnames=keys,extrasaction="ignore"); writer.writeheader(); writer.writerows(item.rows)
        messagebox.showinfo("Export complete",f"Saved {item.readings:,} readings to:\n{path}")

    def import_files(self):
        paths=filedialog.askopenfilenames(title="Add previous MoldSense tests",filetypes=(("MoldSense data","*.csv *.bmerawdata"),("CSV logs","*.csv"),("BME raw captures","*.bmerawdata")))
        if not paths:return
        added=0
        for path_text in paths:
            path=Path(path_text)
            if path.suffix.lower() not in (".csv",".bmerawdata"):continue
            self.store.archive("/"+path.name,path.read_bytes(),"Local file"); added+=1
        self.refresh_data(); messagebox.showinfo("Files added",f"Added {added} dataset file(s) to the local MoldSense library.")

    def _recent_open(self,_event=None):
        selection=self.recent_tree.selection(); item=next((entry for entry in self.catalog if selection and entry.key==selection[0]),None)
        if item:self.primary_var.set(item.name); self.show_view("explore"); self.update_chart()
    def _open_reference_overlay(self):
        self.primary_var.set(next((item.name for item in self.catalog if "Tailored" in item.name),"")); self.compare_var.set(next((item.name for item in self.catalog if "Cap 2 ·" in item.name),"")); self.overlay_var.set(True); self.metric_var.set("Gas resistance"); self.means_var.set(True); self.show_view("explore"); self.update_chart()
    def open_logs(self):
        try:os.startfile(str(self.store.archives))
        except AttributeError:subprocess.Popen(["open" if sys.platform=="darwin" else "xdg-open",str(self.store.archives)])
    def close_app(self):
        if self.device:
            try:self.device.close()
            except Exception:pass
        self.store.db.close(); self.destroy()


def main():MoldSenseApp().mainloop()
