# SrRobs — GitHub Setup (13 repos)

> Lê este ficheiro no teu PC antes de correres qualquer .bat

## 0) Revoga o token velho (URGENTE)

O token fine-grained antigo chegou a ser colado num chat — assume-o comprometido e revoga-o (nunca colar tokens no chat).
1. Vai em https://github.com/settings/tokens
2. Apaga o token `srrobs-cleanup` (fine-grained) — clica `Delete`
3. Eu já apaguei o ficheiro `.gh_token` no workspace com `shred`, mas o chat ainda tem o texto.

## 1) Cria o token novo (classic)

- Vai em https://github.com/settings/tokens/new
- Escolhe **Generate new token (classic)** — é importante ser classic, não fine-grained
- Note: `srrobs-classic`
- Expiration: `7 days`
- Marca: `repo` (tudo dentro) + `delete_repo` + `workflow`
- `Generate token` → copia o `ghp_...` (guarda num .txt temporário, não no chat se possível)

## 2) Cria os 13 repos + limpa o antigo

No **Git PowerShell ou CMD**, cola:

```
gh auth login --with-token < ghp_seu_token.txt
```

Ou, sem instalar `gh`, executa o `1-criar-repos.bat` que está nesta pasta — ele usa `curl` e só precisa do `ghp_...` que vais colar quando pedir.

Ele vai:
- Apagar `Spoon-Knife` (o único repo atual, fork demo de 2022)
- Criar 13 repos novos já públicos com README inicial:
  01 srrobs-skin-trader-pro
  02 steamgamessnipe-free-games
  03 robos-farmer-cs2
  04 okx-supertrend-scanner
  05 pinecode-confluence-engine
  06 kronos-klines-ai
  07 fimathe-cycle-pcm
  08 pokemmo-srrobs
  09 bets-converter-paqbet
  10 mt2robs-lite
  11 tbh-toolkit-5contas
  12 csgo500-sessao-500-lab
  13 srrobs-portfolio (este site)

## 3) Sobe o código real de D:\ (push)

Corre o `2-push-all-12.bat` — ele entra em cada pasta de `D:\` e faz `git init → add → commit → push` para o repo certo.

Se alguma pasta não existir, ele salta e avisa.

## 4) Apaga o token no fim

Volta em https://github.com/settings/tokens e `Delete` no `srrobs-classic`.
O Git guarda credencial no Windows Credential Manager — podes limpar com `cmdkey /list:git:https://github.com` e `cmdkey /delete:...` se quiseres.

---

Precisas de ajuda? Cola o erro exato do terminal aqui no chat (sem colar o token de novo).
