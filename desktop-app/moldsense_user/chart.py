from __future__ import annotations

import math
import tkinter as tk

from .analysis import METRICS, metric_value

INK="#17332F"; MUTED="#6E817D"; GRID="#DDE8E4"; TEAL="#0F8B78"; CORAL="#F07F6A"; WHITE="#FFFFFF"


class TrendChart(tk.Canvas):
    def __init__(self,master,**kwargs):
        super().__init__(master,bg=WHITE,highlightthickness=0,cursor="crosshair",**kwargs)
        self.primary=[]; self.comparison=[]; self.metric="iaq"; self.labels=("Primary","Comparison"); self.means=False; self._plot=(58,34,400,260); self._raw=([],[])
        self.bind("<Configure>",lambda _e:self.draw()); self.bind("<Motion>",self._hover); self.bind("<Leave>",lambda _e:self.delete("hover"))

    def set_data(self,primary,metric,comparison=None,labels=None,means=False):
        self.primary=primary or []; self.comparison=comparison or []; self.metric=metric; self.labels=labels or ("Primary","Comparison"); self.means=means; self.draw()

    def _series(self,rows): return [value for row in rows if (value:=metric_value(row,self.metric)) is not None]
    def _format(self,value):
        if self.metric=="gas_ohms":
            if value>=1_000_000:return f"{value/1_000_000:.2f} MΩ"
            if value>=1_000:return f"{value/1_000:.1f} kΩ"
            return f"{value:.0f} Ω"
        return f"{value:.2f} {METRICS[self.metric][1]}"

    def draw(self):
        self.delete("all"); w=max(self.winfo_width(),560); h=max(self.winfo_height(),320); left,top,right,bottom=66,36,w-24,h-52; self._plot=(left,top,right,bottom)
        raw_a,raw_b=self._series(self.primary),self._series(self.comparison); self._raw=(raw_a,raw_b)
        if not raw_a:
            self.create_text(w/2,h/2-12,text="No readings for this metric",fill=INK,font=("Segoe UI Semibold",15)); self.create_text(w/2,h/2+16,text="Choose another dataset or signal above.",fill=MUTED,font=("Segoe UI",10)); return
        plot_a=[math.log10(v) for v in raw_a if v>0] if self.metric=="gas_ohms" else raw_a[:]
        plot_b=[math.log10(v) for v in raw_b if v>0] if self.metric=="gas_ohms" else raw_b[:]
        values=plot_a+plot_b; lo,hi=min(values),max(values)
        margin=(hi-lo)*.08 if hi!=lo else 1; lo-=margin; hi+=margin
        for i in range(5):
            y=top+(bottom-top)*i/4; axis=hi-(hi-lo)*i/4; shown=10**axis if self.metric=="gas_ohms" else axis
            self.create_line(left,y,right,y,fill=GRID); self.create_text(left-10,y,text=self._format(shown).replace(" "+METRICS[self.metric][1],""),anchor="e",fill=MUTED,font=("Segoe UI",9))
        for i in range(5):
            x=left+(right-left)*i/4; self.create_text(x,bottom+18,text=f"{int(i*100/4)}%",fill=MUTED,font=("Segoe UI",9))
        self.create_line(left,bottom,right,bottom,fill="#B9CBC5"); self.create_line(left,top,left,bottom,fill="#B9CBC5")
        for series,color in ((plot_a,TEAL),(plot_b,CORAL)):
            if len(series)<2:continue
            draw_series=series[::max(1,len(series)//1200)]
            points=[]
            for i,value in enumerate(draw_series): points.extend((left+(right-left)*i/(len(draw_series)-1),bottom-(bottom-top)*(value-lo)/(hi-lo)))
            self.create_line(*points,fill=color,width=2,smooth=len(draw_series)<350)
        if self.means:
            for raw,color,label in ((raw_a,TEAL,self.labels[0]),(raw_b,CORAL,self.labels[1])):
                if not raw:continue
                mean=sum(raw)/len(raw); plotted=math.log10(mean) if self.metric=="gas_ohms" else mean; y=bottom-(bottom-top)*(plotted-lo)/(hi-lo)
                self.create_line(left,y,right,y,fill=color,width=2,dash=(7,5)); self.create_text(left+8,y-9,text=f"{label} mean · {self._format(mean)}",anchor="w",fill=color,font=("Segoe UI Semibold",9))
        if raw_b:
            self.create_oval(right-224,12,right-214,22,fill=TEAL,outline=""); self.create_text(right-208,17,text=self.labels[0],anchor="w",fill=INK,font=("Segoe UI",9))
            self.create_oval(right-108,12,right-98,22,fill=CORAL,outline=""); self.create_text(right-92,17,text=self.labels[1],anchor="w",fill=INK,font=("Segoe UI",9))
        self.create_text(left,16,text=f"{METRICS[self.metric][0]} trend"+(" · logarithmic scale" if self.metric=="gas_ohms" else ""),anchor="w",fill=INK,font=("Segoe UI Semibold",11))
        self._range=(lo,hi)

    def _hover(self,event):
        self.delete("hover"); left,top,right,bottom=self._plot
        if not(left<=event.x<=right and top<=event.y<=bottom):return
        self.create_line(event.x,top,event.x,bottom,fill="#91A8A1",dash=(3,4),tags="hover")
        lines=[]
        for raw,label in zip(self._raw,self.labels):
            if raw:
                index=round((event.x-left)/(right-left)*(len(raw)-1)); lines.append(f"{label}: {self._format(raw[index])}")
        if not lines:return
        x=min(event.x+12,right-210); y=max(top+8,event.y-40); self.create_rectangle(x,y,x+202,y+18+18*len(lines),fill=INK,outline="",tags="hover")
        for i,line in enumerate(lines):self.create_text(x+10,y+14+i*18,text=line,anchor="w",fill=WHITE,font=("Segoe UI",9),tags="hover")
