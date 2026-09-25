import UnityPy

env = UnityPy.load(r"C:\Program Files (x86)\Steam\steamapps\common\TaskbarHero\TaskBarHero_Data\level0")

alvo = ["SkillDurationIncrease", "ElementalDodgeChance"]
achados = 0
for obj in env.objects:
    if obj.type.name != "MonoBehaviour":
        continue
    try:
        d = obj.read()
        tr = d.read_typetree() if hasattr(d, "read_typetree") else None
    except Exception:
        continue
    if tr is None:
        continue
    txt = str(tr)
    for a in alvo:
        if a in txt:
            print("=== MonoBehaviour com", a, "===")
            import json
            s = json.dumps(tr, indent=1, default=str)
            print(s[:1500])
            achados += 1
            break
    if achados >= 2:
        break
