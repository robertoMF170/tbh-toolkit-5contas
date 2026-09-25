import re
import os

s = open('tbhdata/tbhSkillTree-17DFdMtN.js', encoding='utf-8').read()
heroes = {}
for m in re.finditer(r'(\d{3}):\{name:`([A-Za-z]+)`,tiers:\[', s):
    heroes[int(m.group(1))] = m.group(2)

varmap = {101: 'l', 201: 'u', 301: 'd', 401: 'f', 501: 'p', 601: 'm'}
print('herois no jogo:', heroes)

os.makedirs('icons_chars', exist_ok=True)
for code, var in varmap.items():
    name = heroes.get(code)
    if not name:
        print('sem nome para', code)
        continue
    src = f'icons_chars/{var}.webp'
    dst = f'icons_chars/{name.lower()}.webp'
    if os.path.exists(src):
        os.replace(src, dst)
        print(f'{code} {name} -> {dst}')
