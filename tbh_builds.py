import re
import sys
import io
from urllib.request import urlopen, Request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
P_TAG = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
H1_TAG = re.compile(r"<h1[^>]*>(.*?)</h1>", re.S)
H2_TAG = re.compile(r"<h2[^>]*>(.*?)</h2>", re.S)
HTML_TAG = re.compile(r"<[^>]+>")


def clean(s: str) -> str:
    s = HTML_TAG.sub("", s)
    return s.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"').strip()


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return ""
    if not url.startswith("http"):
        url = "https://" + url
    return url


def fetch(url: str) -> str:
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_build(html: str, url: str) -> dict:
    build = {"url": url, "title": "?", "author": "", "date": "", "hero": "", "gear": [], "skills": [], "priority": []}

    m = H1_TAG.search(html)
    if m:
        build["title"] = clean(m.group(1))

    ma = re.search(r'by\s+([^<·]+?)\s*·\s*([A-Za-zç]+ \d+, \d{4})', clean(html))
    if ma:
        build["author"] = ma.group(1).strip()
        build["date"] = ma.group(2).strip()

    for h in H2_TAG.findall(html):
        hc = clean(h)
        if re.match(r".+\(level \d+\)", hc):
            build["hero"] = hc
            break

    for p in P_TAG.findall(html):
        pc = clean(p)
        if pc.startswith("Gear:"):
            build["gear"] = [g.strip() for g in pc[len("Gear:"):].split(",") if g.strip()]
        elif pc.startswith("Skills:"):
            for item in pc[len("Skills:"):].split(","):
                item = item.strip()
                sm = re.match(r"(.+?)\s+(\d+)$", item)
                if sm:
                    build["skills"].append((sm.group(1).strip(), int(sm.group(2))))
                elif item:
                    build["skills"].append((item, None))
        elif pc.startswith("Stat priority:"):
            build["priority"] = [g.strip() for g in pc[len("Stat priority:"):].split(",") if g.strip()]

    return build


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text).strip("-")
    return text[:60] or "build"


def show_build(b: dict) -> str:
    lines = []
    w = 64
    lines.append("=" * w)
    lines.append(b["title"])
    meta = []
    if b["author"]:
        meta.append("por " + b["author"])
    if b["date"]:
        meta.append(b["date"])
    if meta:
        lines.append(" · ".join(meta))
    if b["hero"]:
        lines.append("Heroi: " + b["hero"])
    lines.append(b["url"])
    lines.append("=" * w)

    lines.append("")
    lines.append("ARVORE DE RUNAS (ordem do autor da build)")
    lines.append("-" * w)
    if b["skills"]:
        for i, (name, lvl) in enumerate(b["skills"], 1):
            lvl_txt = f" -> nivel {lvl}" if lvl is not None else ""
            lines.append(f" {i:>2}. [ ] {name}{lvl_txt}")
        finals = {}
        for name, lvl in b["skills"]:
            if lvl is not None:
                finals[name] = max(finals.get(name, 0), lvl)
        total = sum(finals.values())
        lines.append("-" * w)
        lines.append(f" RESUMO FINAL: {', '.join(f'{n} {l}' for n, l in finals.items())}")
        lines.append(f" Total de niveis de runas a comprar: {total}")
    else:
        lines.append(" (sem skills encontradas nesta build)")

    lines.append("")
    lines.append("GEAR")
    lines.append("-" * w)
    if b["gear"]:
        for g in b["gear"]:
            lines.append("  - " + g)

    lines.append("")
    lines.append("STAT PRIORITY (rerolls de equipamento)")
    lines.append("-" * w)
    if b["priority"]:
        for i, g in enumerate(b["priority"], 1):
            lines.append(f" {i:>2}. {g}")

    lines.append("")
    return "\n".join(lines)


def main():
    urls = [normalize_url(a) for a in sys.argv[1:]]
    if not urls:
        print("Cola o(s) link(s) da build (Enter vazio para sair):")
        while True:
            u = normalize_url(input("> "))
            if not u:
                break
            urls.append(u)

    for url in urls:
        try:
            html = fetch(url)
            b = parse_build(html, url)
            out = show_build(b)
            print(out)
            fname = slugify(b["title"]) + ".txt"
            with open(fname, "w", encoding="utf-8") as f:
                f.write(out)
            print(f"(guardado em: {fname})")
        except Exception as e:
            print(f"Erro ao processar {url}: {e}")


if __name__ == "__main__":
    main()
