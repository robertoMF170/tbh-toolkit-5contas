import re

s = open('tbhdata/statsReference-CKw_QSFM.js', encoding='utf-8').read()

# mapa completo statType -> Passive_*
pares = re.findall(r'([A-Za-z]+):`([A-Za-z_]+)`', s)
out = [f'pares no ficheiro: {len(pares)}']
for k, v in pares:
    out.append(f'  {k} -> {v}')

with open(r'C:\Users\Robs\AppData\Local\Temp\opencode\statsref2.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print('ok')
