import UnityPy

GAME = r"C:\Program Files (x86)\Steam\steamapps\common\TaskbarHero\TaskBarHero_Data"

for arquivo in ["level0", "resources.assets", "globalgamemanagers.assets"]:
    env = UnityPy.load(GAME + "\\" + arquivo)
    nomes = {}
    for obj in env.objects:
        try:
            n = obj.type.name
        except Exception:
            continue
        nomes[n] = nomes.get(n, 0) + 1
    print(arquivo, dict(sorted(nomes.items(), key=lambda x: -x[1])[:12]))
    # nomes de TextAsset/MonoBehaviour relevantes
    for obj in env.objects:
        if obj.type.name in ("TextAsset", "MonoBehaviour"):
            try:
                d = obj.read()
                nm = getattr(d, "m_Name", "") or ""
                if any(x in str(nm).lower() for x in ("lang", "local", "i18n", "locale", "translation", "pt")):
                    print("   CANDIDATO:", obj.type.name, nm)
            except Exception:
                pass
