import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch, Circle
RED="#d62828"; BLUE="#1f5fbf"; CASE="#d9d4c7"; PCB="#3aa860"; PORT="#9aa3ab"
def dim(ax,a,b,label,off=(0,0),c=RED,fs=13):
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle="<|-|>",mutation_scale=12,color=c,lw=1.6,zorder=9))
    ax.text((a[0]+b[0])/2+off[0],(a[1]+b[1])/2+off[1],label,color=c,fontsize=fs,fontweight="bold",ha="center",va="center",
            bbox=dict(fc="white",ec="none",pad=1.5),zorder=10)
def ext(ax,p,q): ax.plot([p[0],q[0]],[p[1],q[1]],color=RED,lw=0.7,ls=":",zorder=8)
fig,(a1,a2)=plt.subplots(1,2,figsize=(15,6.4),gridspec_kw=dict(width_ratios=[1,1.25]))
# ---- top view
ax=a1; ax.set_title("1. From above (no top cover)",fontsize=13,loc="left")
ax.add_patch(Rectangle((0,0),95,66,fc=CASE,ec="#555",lw=1.2))
ax.add_patch(Rectangle((3,3),89,60,fc="#efebe0",ec="#888",lw=0.6))
ax.add_patch(Rectangle((5,5),85,56,fc=PCB,ec="#1d5c33",lw=1))
for y in (7,25,43): ax.add_patch(Rectangle((73,y),21,15 if y>7 else 16,fc=PORT,ec="#555"))
ax.text(83.5,15,"Ethernet",ha="center",fontsize=7); ax.text(83.5,33,"USB",ha="center",fontsize=7); ax.text(83.5,50,"USB",ha="center",fontsize=7)
ax.add_patch(Rectangle((11,1),8,6,fc=PORT,ec="#555")); ax.text(15,9,"power",ha="center",fontsize=7)
ax.text(40,35,"Pi 3",color="white",fontsize=12,ha="center")
dim(ax,(0,-9),(95,-9),"A  length (outside)",off=(0,-5)); ext(ax,(0,0),(0,-11)); ext(ax,(95,0),(95,-11))
dim(ax,(-9,0),(-9,66),"B",off=(-6,0)); ext(ax,(0,0),(-11,0)); ext(ax,(0,66),(-11,66))
ax.text(-24,33,"width\n(outside)",color=RED,fontsize=10,ha="center",va="center",rotation=90)
ax.text(100,33,"USB /\nEthernet\nend",fontsize=9,va="center")
ax.set_xlim(-32,118); ax.set_ylim(-24,78); ax.set_aspect("equal"); ax.axis("off")
# ---- side view (drawn 2x for readability)
ax=a2; ax.set_title("2. From the side (looking at the long side, on a flat table)",fontsize=13,loc="left")
k=2.0
def R(x,y,w,h,**kw): ax.add_patch(Rectangle((x*k,y*k),w*k,h*k,**kw))
ax.plot([-20*k,112*k],[0,0],color="#333",lw=2); ax.text(60*k,-4*k,"table",fontsize=9,color="#333")
F=2.0; W=10.0
for x in (8,78): R(x,0,8,F,fc="#444")
R(0,F,95,2,fc=CASE,ec="#555"); R(0,F,2,W,fc=CASE,ec="#555"); R(93,F,2,W,fc=CASE,ec="#555")
for x in (5,63): R(x,F+2,3,4,fc=CASE,ec="#555")
bz=F+6; R(3,bz,85,1.6,fc=PCB,ec="#1d5c33")
R(70,bz+1.6,25,15.5,fc=PORT,ec="#555"); ax.text(82.5*k,(bz+9)*k,"USB",ha="center",fontsize=9)
R(22,bz+1.6,36,2.5,fc="#2a2a2a")
ax.text(40*k,(bz+6)*k,"Pi 3 (in the cover)",fontsize=9,ha="center",color="#1d5c33")
# C: cover wall height, at the left end
dim(ax,(-6*k,0),(-6*k,(F+W)*k),"C",off=(-4*k,0)); ext(ax,(0,(F+W)*k),(-8*k,(F+W)*k))
ax.text(-12*k,(F+W)/2*k,"cover wall height\n(table to top edge)",color=RED,fontsize=9,ha="right",va="center")
# D: table to bottom of USB ports, at the right end
dim(ax,(101*k,0),(101*k,(bz+1.6)*k),"D",c=BLUE,off=(4*k,0)); ext(ax,(95*k,(bz+1.6)*k),(103*k,(bz+1.6)*k))
ax.text(108*k,(bz+1.6)/2*k,"table to the BOTTOM\nof the USB ports",color=BLUE,fontsize=9,va="center")
# E: feet
ax.annotate("E  feet / bumps underneath:\n    how tall, and where",(12*k,F/2*k),(20*k,-14*k),color=RED,fontsize=10,fontweight="bold",
            arrowprops=dict(arrowstyle="-|>",color=RED,lw=0.9))
ax.set_xlim(-45*k,150*k); ax.set_ylim(-20*k,32*k); ax.set_aspect("equal"); ax.axis("off")
fig.text(0.02,0.04,"F  Also tell me: is the USB/Ethernet end of the cover open, or are there cut-outs around each port?  Can you plug the power (micro-USB) in through the side?\n"
         "Measure in mm, outside to outside. A ruler is fine. The shapes are a sketch; your case may look different.",fontsize=11)
fig.suptitle("What to measure on the Pi's bottom cover (with the Pi in it)",fontsize=15,fontweight="bold",x=0.02,ha="left")
plt.tight_layout(rect=(0,0.08,1,0.95)); plt.savefig(f"{__import__('sys').argv[1]}/measure_case.png",dpi=110,facecolor="white")
