import re

g = open('tbhdata/game-data-qWh3M14n.js', encoding='utf-8').read()
out = []

# como estao identificadas as imagens?
for m in list(re.finditer(r'([A-Za-z0-9_$`\'"]{1,40})\s*[=:]\s*`?data:image/(png|webp);base64,', g))[:15]:
    out.append('CHAVE: ' + repr(m.group(1)) + ' (' + m.group(2) + ')')

# contexto alargado da primeira
i = g.find('data:image')
out.append('CONTEXTO 1a: ' + g[max(0, i - 200):i + 60])

# cabecalho do ficheiro
out.append('HEADER: ' + g[:400])

with open(r'C:\Users\Robs\AppData\Local\Temp\opencode\gamedata2.txt', 'w', encoding='utf-8') as f:
    f.write('\n\n'.join(out))
print('ok')
