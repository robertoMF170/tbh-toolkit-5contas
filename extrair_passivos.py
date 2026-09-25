import UnityPy
import os

GAME = r"C:\Program Files (x86)\Steam\steamapps\common\TaskbarHero\TaskBarHero_Data"
env = UnityPy.load(GAME + r"\sharedassets0.assets")

os.makedirs("icons_passivos", exist_ok=True)
achados = {}
for obj in env.objects:
    if obj.type.name != "Sprite":
        continue
    try:
        d = obj.read()
        nm = str(getattr(d, "m_Name", "") or "")
    except Exception:
        continue
    if nm.startswith("Passive_") or nm.startswith("Active_") or nm.startswith("Skill_"):
        if nm in achados:
            continue
        try:
            img = d.image
            img.save(f"icons_passivos/{nm}.png")
            achados[nm] = True
        except Exception as e:
            print("erro", nm, str(e)[:60])

print("extraidos:", len(achados))
for n in sorted(achados):
    print("  ", n)
