# -*- coding: utf-8 -*-
# Patch temporario: insere prompt [I]niciar/[S]altar quando a conta NAO esta a correr.
import io

PATH = "src/abrir_steam.py"

with io.open(PATH, "r", encoding="utf-8", newline="") as f:
    raw = f.read()
raw = raw.replace("\r\n", "\n")
lines = raw.split("\n")

NAT_ANCHOR = '        steam = r"C:\\Program Files (x86)\\Steam\\steam.exe"'
BOX_ANCHOR = "    if not acc:"

nat_hits = [i for i, l in enumerate(lines) if l == NAT_ANCHOR]
box_hits = [i for i, l in enumerate(lines) if l == BOX_ANCHOR]
assert len(nat_hits) == 1, ("ancora nativa", nat_hits)
assert len(box_hits) == 1, ("ancora sandbox", box_hits)

# guarda: ja foi aplicado antes?
if any("Queres [I]niciar agora" in l for l in lines):
    print("JA APLICADO - nada a fazer")
    raise SystemExit(0)

nat = [
    '        elif not forcar:',
    '            r = "i"',
    '            if sys.stdin.isatty():',
    '                print(f"[nativa] {info[\'nome\']} NAO está a correr ({motivo}).")',
    '                print("         Queres [I]niciar agora ou [S]altar esta conta? [I/S, enter=I]: ", end="")',
    '                try:',
    '                    r = input().strip().lower()',
    '                except EOFError:',
    '                    r = "i"',
    '            if r in ("s", "saltar", "skip"):',
    '                print("         -> a saltar (fica parada).")',
    '                return',
    '            print("         -> a iniciar " + info["nome"] + "...")',
]

box = [
    '    elif not forcar:',
    '        r = "i"',
    '        if sys.stdin.isatty():',
    '            print(f"[{box}] NAO está a correr ({motivo}).")',
    '            print("      Queres [I]niciar agora ou [S]altar esta conta? [I/S, enter=I]: ", end="")',
    '            try:',
    '                r = input().strip().lower()',
    '            except EOFError:',
    '                r = "i"',
    '        if r in ("s", "saltar", "skip"):',
    '            print("      -> a saltar (fica parada).")',
    '            return',
    '        print(f"[{box}] -> a iniciar...")',
    '',
]

# inserir do fim para o inicio (indices nao deslocam)
i_nat = nat_hits[0]
i_box = box_hits[0]
assert i_nat < i_box
lines[i_box:i_box] = box
lines[i_nat:i_nat] = nat

out = "\n".join(lines)
with io.open(PATH, "w", encoding="utf-8", newline="") as f:
    f.write(out)
print("OK: blocos I/S inseridos (nativa antes da linha steam, sandbox antes de 'if not acc:')")
