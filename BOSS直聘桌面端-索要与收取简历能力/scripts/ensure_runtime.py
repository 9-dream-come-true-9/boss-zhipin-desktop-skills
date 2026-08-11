"""Verify global Python runtime for the Skill; never creates a private environment."""
import importlib.util,json,sys
REQUIRED=["pywinauto","psutil","win32api","comtypes","docx","pypdf"]
missing=[x for x in REQUIRED if importlib.util.find_spec(x) is None]
print(json.dumps({"python":sys.executable,"version":sys.version,"missing":missing},ensure_ascii=False))
raise SystemExit(1 if missing else 0)
