import re
import json
import base64
import os

g = open('tbhdata/game-data-qWh3M14n.js', encoding='utf-8').read()
m = re.search(r'SPRITES[^`]*?JSON\.parse\(`(\{.*?\})`\)', g, re.S)
if not m:
    # alternativa: procurar o bloco que comeca por {"AMULET_
    m = re.search(r'JSON\.parse\(`(\{"AMULET_.*?)`\)', g, re.S)
blob = m.group(1)
spr = json.loads(blob)
print('sprites:', len(spr))

fam = {}
for k in spr:
    fam.setdefault(k.split('_')[0], 0)
    fam[k.split('_')[0]] += 1
print('familias:', dict(sorted(fam.items(), key=lambda x: -x[1])))

os.makedirs('icons_sprites', exist_ok=True)
for k, v in spr.items():
    b64 = v.split(',', 1)[1]
    ext = 'webp' if 'webp' in v.split(',')[0] else 'png'
    with open(f'icons_sprites/{k}.{ext}', 'wb') as f:
        f.write(base64.b64decode(b64))
print('guardados em icons_sprites/')
