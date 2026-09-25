import UnityPy

GAME = r"C:\Program Files (x86)\Steam\steamapps\common\TaskbarHero\TaskBarHero_Data"
KEYS = ("skill", "rune", "icon", "blessing", "attack", "meteor", "hydra", "arrow", "heal", "stat")

for arquivo in ["resources.assets", "sharedassets0.assets", "globalgamemanagers.assets"]:
    env = UnityPy.load(GAME + "\\" + arquivo)
    hits = []
    for obj in env.objects:
        if obj.type.name in ("Sprite", "Texture2D"):
            try:
                nm = str(getattr(obj.read(), "m_Name", "") or "")
            except Exception:
                continue
            low = nm.lower()
            if any(k in low for k in KEYS):
                hits.append((obj.type.name, nm))
    print(arquivo, '->', len(hits), 'candidatos')
    for t, n in sorted(set(hits))[:80]:
        print('   ', t, n)
