import tbh_arvore as ta

data = ta.load_game_data()
out = ['ATIVAS (id -> nome):']
for aid in sorted(data["actives"]):
    a = data["actives"][aid]
    out.append(f'{aid} {a["name"]} max{a["maxLevel"]}')

stats = sorted({p["statType"] for p in data["passives"].values()})
out.append('')
out.append('STATS (' + str(len(stats)) + '): ' + ', '.join(stats))

with open(r'C:\Users\Robs\AppData\Local\Temp\opencode\nomes.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print('ok')
