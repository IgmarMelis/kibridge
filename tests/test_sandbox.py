"""AST validator tests for kibridge.script_runner."""
import os
import sys
import types

# Stub pcbnew + wx so importing kibridge doesn't fail in CI.
pcbnew = types.ModuleType("pcbnew")
class _AP:
    def register(self): pass
pcbnew.ActionPlugin = _AP
pcbnew.F_SilkS = 0; pcbnew.B_SilkS = 1; pcbnew.F_Fab = 2; pcbnew.B_Fab = 3
pcbnew.User_1 = 4; pcbnew.F_Cu = 5; pcbnew.B_Cu = 6
pcbnew.PCB_VIA_T = 99; pcbnew.SHAPE_T_CIRCLE = 1
sys.modules["pcbnew"] = pcbnew

wx = types.ModuleType("wx")
for n in ("OK","ICON_WARNING","ICON_INFORMATION","ICON_ERROR",
          "ICON_QUESTION","YES_NO","YES","NO"):
    setattr(wx, n, 1)
wx.MessageBox = lambda *a, **k: 1
sys.modules["wx"] = wx

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "plugin"))

from kibridge.script_runner import validate_script, ScriptValidationError

GOOD = [
    "import kibridge_api\nkibridge_api.list_nets()\n",
    "from kibridge_api import list_nets\nlist_nets()\n",
    "import kibridge_api\nfor n in kibridge_api.list_nets():\n    print(n)\n",
    "import kibridge_api\nkibridge_api.add_silkscreen_note('hi', 1.0, 2.0)\n",
]

BAD = [
    ("import os", "imports os"),
    ("import kibridge_api, os", "imports os in second"),
    ("from os import path", "from os"),
    ("import pcbnew", "imports pcbnew"),
    ("import sys", "imports sys"),
    ("import subprocess", "imports subprocess"),
    ("import socket", "imports socket"),
    ("eval('1+1')", "eval"),
    ("exec('print(1)')", "exec"),
    ("compile('1', 'a', 'eval')", "compile"),
    ("open('/etc/passwd').read()", "open"),
    ("__import__('os')", "__import__"),
    ("import kibridge_api\nkibridge_api.__class__", "dunder access"),
    ("import kibridge_api\nx = kibridge_api.__dict__", "dunder dict"),
    ("import kibridge_api\ngetattr(kibridge_api, '_log')", "getattr"),
    ("import kibridge_api\nsetattr(kibridge_api, 'x', 1)", "setattr"),
    ("import kibridge_api\nbreakpoint()", "breakpoint"),
    ("import kibridge_api\nx = globals()", "globals()"),
]

print("=== GOOD scripts (should validate) ===")
for src in GOOD:
    try:
        validate_script(src)
        print(f"  OK    {src.splitlines()[0]!r}")
    except ScriptValidationError as e:
        print(f"  FAIL  {src.splitlines()[0]!r}: {e}")
        sys.exit(1)

print("\n=== BAD scripts (should be refused) ===")
for src, label in BAD:
    try:
        validate_script(src)
        print(f"  LEAK  {label}: validator passed forbidden code!")
        sys.exit(1)
    except ScriptValidationError as e:
        print(f"  OK    {label}: refused")

print("\nAll AST validation tests passed.")
