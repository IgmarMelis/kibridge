"""End-to-end test against the renamed kibridge package."""
import os, sys, types, json, shutil, tempfile

# --- Fake pcbnew ----------
pcbnew = types.ModuleType("pcbnew")
pcbnew.PCB_VIA_T = 99
pcbnew.Edge_Cuts = 44
pcbnew.F_SilkS=10; pcbnew.B_SilkS=11; pcbnew.F_Fab=12; pcbnew.B_Fab=13
pcbnew.User_1=14; pcbnew.F_Cu=0; pcbnew.B_Cu=31; pcbnew.SHAPE_T_CIRCLE=1
class _AP:
    def register(self): pass
pcbnew.ActionPlugin = _AP
pcbnew.GetBuildVersion = lambda: "FAKE-10.0.1"
class FakeVec:
    def __init__(self, x, y): self.x = x; self.y = y
pcbnew.VECTOR2I = FakeVec

class _PCBText:
    def __init__(self, b): self.text=""; self.layer=None; self.pos=None
    def SetText(self,t): self.text=t
    def SetLayer(self,l): self.layer=l
    def SetPosition(self,v): self.pos=v
    def SetTextSize(self,v): pass
class _PCBShape:
    def __init__(self,b): pass
    def SetShape(self,s): pass
    def SetLayer(self,l): pass
    def SetCenter(self,v): pass
    def SetEnd(self,v): pass
    def SetWidth(self,w): pass
class _PCBVia:
    def __init__(self,b): pass
    def SetPosition(self,v): pass
    def SetWidth(self,w): pass
    def SetDrill(self,d): pass
    def SetNetCode(self,c): pass
    def SetLayerPair(self,a,b): pass
pcbnew.PCB_TEXT = _PCBText
pcbnew.PCB_SHAPE = _PCBShape
pcbnew.PCB_VIA = _PCBVia

# --- Fake wx ----------
wx = types.ModuleType("wx")
for n in ("OK","ICON_WARNING","ICON_INFORMATION","ICON_ERROR","ICON_QUESTION","YES_NO","YES","NO"):
    setattr(wx, n, 1)
wx.MessageBox = lambda *a, **k: 1
sys.modules["pcbnew"] = pcbnew
sys.modules["wx"] = wx

applied_items = []

# --- Fake board ----------
class FakeNet:
    def __init__(self,c,n): self.code,self.name=c,n
    def GetNetname(self): return self.name
    def GetNetCode(self): return self.code

class FakePad:
    def __init__(self,c,n): self.code,self.net=c,n
    def GetNetCode(self): return self.code
    def GetNet(self): return self.net

class FakeFP:
    def __init__(self,r,v,l,x,y,pads):
        self._r,self._v,self._l=r,v,l
        self._x,self._y=x,y; self._pads=pads
    def GetReference(self): return self._r
    def GetValue(self): return self._v
    def GetLayer(self): return self._l
    def GetOrientationDegrees(self): return 0.0
    def Pads(self): return self._pads
    def GetPosition(self):
        return type("P",(),{"x":self._x,"y":self._y})()

class FakeTrack:
    def __init__(self,c,n,w,L,sx,sy,ex,ey,layer):
        self.code,self.net=c,n; self._w,self._len=w,L
        self._s,self._e=(sx,sy),(ex,ey); self._layer=layer
        self._modified_width=None; self._selected=False
    def Type(self): return 1
    def GetNetCode(self): return self.code
    def GetNet(self): return self.net
    def GetWidth(self): return self._modified_width or self._w
    def SetWidth(self,w): self._modified_width=w; applied_items.append(("track_width",self.code,w))
    def GetLength(self): return self._len
    def GetLayer(self): return self._layer
    def GetStart(self): return type("P",(),{"x":self._s[0],"y":self._s[1]})()
    def GetEnd(self): return type("P",(),{"x":self._e[0],"y":self._e[1]})()
    def GetPosition(self): return type("P",(),{"x":self._s[0],"y":self._s[1]})()
    def SetSelected(self): self._selected=True

class FakeBoardSettings:
    m_TrackMinWidth=200_000
    m_ViasMinSize=600_000
    m_MinThroughDrill=300_000
    m_MinClearance=200_000
    def GetNetClasses(self): raise AttributeError("no NCs")

class FakeBoard:
    def __init__(self,path):
        self._path=path
        gnd=FakeNet(1,"GND"); v5=FakeNet(2,"5V"); v33=FakeNet(3,"3.3v"); sig=FakeNet(4,"SIG_A")
        self._fps=[
            FakeFP("U1","ATmega328P",0,50_000_000,50_000_000,
                   [FakePad(1,gnd),FakePad(2,v5),FakePad(3,v33),FakePad(4,sig)]),
            FakeFP("J1","Conn_01x04",0,80_000_000,30_000_000,
                   [FakePad(1,gnd),FakePad(2,v5),FakePad(3,v33),FakePad(4,sig)]),
        ]
        self._tr=[
            FakeTrack(1,gnd,200_000,10_000_000,50_000_000,50_000_000,60_000_000,50_000_000,0),
            FakeTrack(2,v5, 200_000,20_000_000,50_000_000,51_000_000,70_000_000,51_000_000,0),
            FakeTrack(2,v5, 200_000,15_000_000,70_000_000,51_000_000,80_000_000,51_000_000,0),
            FakeTrack(3,v33,200_000, 5_000_000,50_000_000,52_000_000,55_000_000,52_000_000,0),
            FakeTrack(4,sig,200_000,10_000_000,50_000_000,53_000_000,60_000_000,53_000_000,0),
        ]
        self._settings=FakeBoardSettings()
    def GetFileName(self): return self._path
    def GetFootprints(self): return self._fps
    def GetTracks(self): return self._tr
    def Zones(self): return []
    def GetDrawings(self): return []
    def GetDesignSettings(self): return self._settings
    def GetLayerName(self,lid):
        return {0:"F.Cu",31:"B.Cu",10:"F.SilkS",11:"B.SilkS",
                12:"F.Fab",13:"B.Fab",14:"User.1"}.get(lid,str(lid))
    def Add(self,item): applied_items.append(("add",type(item).__name__))

pcbnew.SaveBoard = lambda p,b: applied_items.append(("save",p)) or open(p,"a").close()
pcbnew.Refresh = lambda: applied_items.append(("refresh",))

# --- Run test ----------
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "plugin"))

tmp = tempfile.mkdtemp(prefix="kibridge_test_")
project = os.path.join(tmp, "MyProject")
os.makedirs(project)
board_path = os.path.join(project, "MyProject.kicad_pcb")
with open(board_path,"w") as f: f.write("(kicad_pcb)\n")

# Seed template into plugin dir for installed-layout lookup
plugin_dir = os.path.join(REPO_ROOT, "plugin", "kibridge")
template_dir = os.path.join(plugin_dir, "workspace_template")
if not os.path.exists(template_dir):
    shutil.copytree(os.path.join(REPO_ROOT, "workspace_template"), template_dir)

from kibridge.workspace_exporter import ensure_workspace, export_snapshot
from kibridge.workspace_applier import load_review, dry_run, apply_real

board = FakeBoard(board_path)
ws = ensure_workspace(board, plugin_dir)
print(f"Workspace: {ws}")
assert "kibridge_workspace" in ws, f"folder not renamed: {ws}"

paths = export_snapshot(board, ws)
print(f"Snapshots: {sorted(os.path.basename(p) for p in paths.values())}")

# Write actions.json with all 6 op types
actions = {
    "schema_version":1, "report_ref":"snapshot/board_inspect.json",
    "summary":"test", "confirm_changes":True,
    "actions":[
        {"op":"add_silkscreen_note","text":"KB: test","x_mm":10.0,"y_mm":10.0,"layer":"F.SilkS","size_mm":1.0},
        {"op":"highlight_net","net_name":"5V"},
        {"op":"set_track_widths_for_net","net_name":"5V","width_mm":0.6},
        {"op":"set_track_widths_for_net","net_name":"3.3v","width_mm":0.4},
        {"op":"add_user_marker","x_mm":50.0,"y_mm":50.0,"radius_mm":1.5,"note":"test"},
        {"op":"add_stitching_via","x_mm":60.0,"y_mm":60.0,"net_name":"GND"},
    ]
}
with open(os.path.join(ws,"review","actions.json"),"w") as f: json.dump(actions,f)

# Sample script using kibridge_api
script = '''import kibridge_api
for net in kibridge_api.list_nets():
    if "GND" in net.upper():
        kibridge_api.highlight_net(net)
'''
script_path = os.path.join(ws,"review","scripts","grounds.py")
os.makedirs(os.path.dirname(script_path), exist_ok=True)
with open(script_path,"w") as f: f.write(script)

review = load_review(ws)
print(f"Loaded: {len(review['actions'])} actions, {len(review['scripts'])} scripts")
preview = dry_run(board, review)
print(f"Dry-run produced {len(preview)} ops")
result = apply_real(board, ws, review)
print(f"Applied: {result['applied']} ops, {len(result['errors'])} errors")
assert result['applied'] >= 7, "expected 7+ ops applied"
assert os.path.isfile(result['backup_path'])
assert "kibridge_backup" in result['backup_path']

v5 = [t._modified_width for t in board._tr if t.code==2]
v33 = [t._modified_width for t in board._tr if t.code==3]
assert all(w == 600_000 for w in v5), f"5V not widened: {v5}"
assert all(w == 400_000 for w in v33), f"3.3v not widened: {v33}"
print("=== KIBRIDGE E2E PASSED ===")
