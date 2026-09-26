import os
import re
import json
import base64
import sys
from urllib.request import urlopen, Request

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
def _first_dir(*cands):
    for p in cands:
        if os.path.isdir(p): return p
    return cands[0]
DATA_DIR = _first_dir(os.path.join(ROOT, "data", "tbhdata"), os.path.join(ROOT, "tbhdata"), os.path.join(BASE, "tbhdata"))
ICON_DIR = _first_dir(os.path.join(ROOT, "assets", "icons"), os.path.join(ROOT, "icons"), os.path.join(BASE, "icons"))
GAME = r"D:\SteamLibrary\steamapps\common\TaskbarHero\TaskBarHero_Data"


def read_asset(key: str) -> str:
    for f in os.listdir(DATA_DIR):
        if f.startswith(key):
            return open(os.path.join(DATA_DIR, f), encoding="utf-8").read()
    raise RuntimeError("falta asset " + key)


def extract_map() -> None:
    import UnityPy
    env = UnityPy.load(os.path.join(GAME, "level0"))
    nodes = {}
    linepos = {}
    for obj in env.objects:
        if obj.type.name != "RectTransform":
            continue
        try:
            t = obj.read()
            name = t.m_GameObject.read().m_Name
        except Exception:
            continue
        ap = t.m_AnchoredPosition
        m = re.match(r"RuneNode_(\d+)$", name)
        if m:
            nodes[int(m.group(1))] = [round(float(ap.x), 1), round(float(ap.y), 1)]
        else:
            m2 = re.match(r"RunePageNodeLine-RuneNode_(\d+)$", name)
            if m2:
                linepos[int(m2.group(1))] = [round(float(ap.x), 1), round(float(ap.y), 1)]

    def nearest(p):
        best, bd = None, 1e18
        for nid, np in nodes.items():
            d = (np[0] - p[0]) ** 2 + (np[1] - p[1]) ** 2
            if d < bd:
                bd, best = d, nid
        return best

    edges = [[nearest(p), tid] for tid, p in linepos.items()]
    with open(os.path.join(DATA_DIR, "rune_tree_map.json"), "w") as f:
        json.dump({"nodes": nodes, "edges": edges}, f)
    print(f"mapa extraido: {len(nodes)} nos, {len(edges)} ligacoes")


def load_runes() -> dict:
    s = read_asset("tbhRunes")
    runes = {}
    for m in re.finditer(r"(\d+):\{label:`([^`]*)`,statLabel:`([^`]*)`,icon:`([^`]*)`\}", s):
        rid, label, stat, icon = int(m.group(1)), m.group(2), m.group(3), m.group(4)
        runes[rid] = {"label": label, "stat": stat, "icon": icon}
    return runes


def load_costs() -> dict:
    s = read_asset("tbhRuneCosts")
    costs = {}
    for m in re.finditer(r"(\d+):\{maxLevel:(\d+),levels:\[(.*?)\]\}", s):
        rid, mx, lv = int(m.group(1)), int(m.group(2)), m.group(3)
        total = sum(int(c) for c in re.findall(r"cost:(\d+)", lv))
        costs[rid] = {"maxLevel": mx, "total": total}
    return costs


def icon_path(icon: str) -> str:
    p = os.path.join(ICON_DIR, icon + ".png")
    if not os.path.exists(p):
        return ""
    pref = "assets/icons/" if "assets" in ICON_DIR else "icons/"
    return pref + icon + ".png"


def icon_b64(icon: str) -> str:
    # compat: devolve path; quem precisa de base64 que carregue o ficheiro
    h = icon_path(icon)
    if not h:
        return ""
    # para nao quebrar callers antigos que esperam data-uri, devolve path (usado como href no SVG)
    return h


def ensure_map() -> dict:
    p = os.path.join(DATA_DIR, "rune_tree_map.json")
    if not os.path.exists(p):
        extract_map()
    return json.load(open(p))


def main():
    mp = ensure_map()
    runes = load_runes()
    costs = load_costs()

    nodes = mp["nodes"]
    edges = mp["edges"]
    xs = [v[0] for v in nodes.values()]
    ys = [v[1] for v in nodes.values()]
    pad = 90
    minx, maxx, miny, maxy = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    W = maxx - minx
    H = maxy - miny

    def sx(x):
        return x - minx

    def sy(y):
        return maxy - y

    parts = []
    parts.append(f'<svg id="map" width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">')
    for src, tid in edges:
        if src not in nodes or tid not in nodes:
            continue
        parts.append(
            f'<line x1="{sx(nodes[src][0]):.0f}" y1="{sy(nodes[src][1]):.0f}" '
            f'x2="{sx(nodes[tid][0]):.0f}" y2="{sy(nodes[tid][1]):.0f}" class="edge"/>'
        )
    missing_icons = set()
    for nid_str, (x, y) in sorted(nodes.items()):
        nid = int(nid_str)
        r = runes.get(nid, {})
        c = costs.get(nid, {})
        icon = r.get("icon", "")
        href = icon_b64(icon)
        if not href and icon:
            missing_icons.add(icon)
        label = r.get("label", "?")
        stat = r.get("stat", "?")
        mx = c.get("maxLevel", "?")
        tot = c.get("total", 0)
        tip = f"{label} | {stat} | max {mx} | custo total {tot:,} ouro".replace(",", ".")
        cx, cy = sx(x), sy(y)
        parts.append(f'<g class="node" data-id="{nid}" transform="translate({cx - 32:.0f},{cy - 32:.0f})"><title>{esc_html(tip)}</title><rect width="64" height="64" rx="14" class="box"/>')
        if href:
            parts.append(f'<image x="10" y="10" width="44" height="44" href="{href}"/>')
        else:
            parts.append(f'<text x="32" y="40" class="q">?</text>')
        parts.append("</g>")
    parts.append('<path id="fullroute" fill="none" stroke="#ffd86b" stroke-width="2" stroke-dasharray="2 10" opacity="0.25"/>')
    parts.append('<path id="route" fill="none" stroke="#ffd86b" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" opacity="0.95"/>')
    parts.append('<g id="badgeLayer"></g>')
    parts.append("</svg>")

    doc = rf"""<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8"><title>Arvore de Runas - mapa real do jogo</title>
<style>
 :root {{ color-scheme: dark; }}
 body {{ margin:0; background:#0e0c0a; color:#e8dcc0; font-family:'Segoe UI',system-ui,sans-serif; overflow:hidden; }}
 header {{ position:fixed; top:0; left:0; right:220px; z-index:10; background:rgba(20,17,12,.95); border-bottom:2px solid #7a6848; padding:10px 20px; }}
 h1 {{ margin:0; font-size:16px; color:#ffd86b; }}
 header p {{ margin:2px 0 0; font-size:12px; color:#a89878; }}
 #viewport {{ position:fixed; inset:0; cursor:grab; }}
 #viewport.drag {{ cursor:grabbing; }}
 #mover {{ transform-origin:0 0; }}
 .edge {{ stroke:#4a4030; stroke-width:3; pointer-events:none; }}
 .box {{ fill:#1d1913; stroke:#8a6d2f; stroke-width:2; transition:.12s; }}
 .node {{ cursor:pointer; }}
 .node:hover .box {{ stroke:#ffd86b; fill:#2a2317; }}
 .node.sel .box {{ stroke:#ffd86b; stroke-width:3.5; fill:#2a2314; }}
 .q {{ fill:#a89878; font-size:30px; text-anchor:middle; }}
 #panel {{ position:fixed; top:0; right:0; bottom:0; width:220px; background:#161310; border-left:2px solid #7a6848; z-index:10; padding:14px; overflow:auto; }}
 #panel h2 {{ margin:0 0 8px; font-size:13px; color:#ffd86b; letter-spacing:1px; }}
 #plist {{ list-style:none; margin:0 0 10px; padding:0; font-size:12px; display:flex; flex-direction:column; gap:5px; }}
 #plist li {{ display:flex; gap:6px; line-height:1.3; }}
 #plist .n {{ color:#ffd86b; font-weight:800; flex:0 0 20px; }}
 #partinfo {{ font-size:12px; font-weight:800; color:#ffd86b; margin:2px 0 6px; }}
 #partbar {{ display:flex; gap:4px; flex-wrap:wrap; margin-bottom:8px; max-height:110px; overflow:auto; }}
 #partbar button {{ background:#241f18; color:#c8b890; border:1px solid #5a4e38; border-radius:6px; padding:4px 7px; font-size:10.5px; font-weight:700; cursor:pointer; }}
 #partbar button.on {{ background:#ffd86b; color:#141210; }}
 .ringbadge {{ fill:#ffd86b; stroke:#141210; stroke-width:2; }}
 .stepnum {{ fill:#141210; font-size:14px; font-weight:800; text-anchor:middle; }}
 #ptotal {{ font-size:15px; font-weight:800; color:#ffd86b; margin:8px 0; }}
 #pclear {{ background:#3a2020; color:#ffb0b0; border:1px solid #7a4040; border-radius:8px; padding:6px 10px; cursor:pointer; font-size:12px; }}
 #phint {{ font-size:11px; color:#a89878; line-height:1.4; }}
</style></head>
<body>
<header><h1>Arvore de Runas — mapa real (posicoes extraidas do jogo)</h1>
<p>CLICA nas runas pela ordem que queres comprar — desenha a tua rota · hover = nome/max/custo · scroll = zoom, arrastar = mover</p></header>
<div id="viewport"><div id="mover">{"".join(parts)}</div></div>
<div id="panel">
  <h2>A TUA ROTA</h2>
  <div id="partinfo"></div>
  <div id="partbar"></div>
  <ol id="plist"></ol>
  <div id="ptotal"></div>
  <button id="pclear">Limpar rota</button>
  <p id="phint">Dividida em PARTES de 15 runas: compra a Parte 1 inteira, depois a 2, etc. Fica guardada no browser.</p>
</div>
<script>
const vp=document.getElementById('viewport'),mv=document.getElementById('mover');
const route=document.getElementById('route'),plist=document.getElementById('plist'),ptotal=document.getElementById('ptotal');
let scale=0.8,tx=60,ty=80,drag=null,moved=false;
let picked=[]; try{{picked=JSON.parse(localStorage.getItem('tbh_rota')||'[]')}}catch(e){{}}
const centers={{}};
document.querySelectorAll('.node').forEach(g=>{{
 const id=g.dataset.id;
 const m=g.getAttribute('transform').match(/translate\(([-\d.]+),([-\d.]+)\)/);
 centers[id]=[parseFloat(m[1])+32,parseFloat(m[2])+32];
 g.addEventListener('mousedown',()=>{{moved=false}});
 g.addEventListener('mouseup',e=>{{if(moved)return;toggle(id)}});
}});
function save(){{localStorage.setItem('tbh_rota',JSON.stringify(picked))}}
function toggle(id){{
 const i=picked.indexOf(id);
 if(i>=0)picked.splice(i,1);else picked.push(id);
 render();
}}
let part=0;const PER=15;
const fullEl=document.getElementById('fullroute'),badgeLayer=document.getElementById('badgeLayer'),partbar=document.getElementById('partbar'),partinfo=document.getElementById('partinfo');
function costOf(id){{
 const g=document.querySelector('.node[data-id="'+id+'"] title');
 const t=g?g.textContent.split('|'):['?','?','?','0'];
 return {{name:t[0].trim(),costTxt:t[3].trim(),num:parseFloat(t[3].replace(/[^\d]/g,''))||0}};
}}
function render(){{
 save();
 const n=Math.max(1,Math.ceil(picked.length/PER));
 if(part>=n)part=n-1;
 document.querySelectorAll('.node').forEach(g=>g.classList.toggle('sel',picked.includes(g.dataset.id)));
 partbar.innerHTML='';
 for(let i=0;i<n;i++){{
  const b=document.createElement('button');b.textContent='PARTE '+(i+1);
  if(i===part)b.classList.add('on');
  b.addEventListener('click',()=>{{part=i;render();}});
  partbar.appendChild(b);
 }}
 partinfo.textContent='Parte '+(part+1)+' de '+n+(picked.length?' — runas '+(part*PER+1)+' a '+Math.min(picked.length,(part+1)*PER):'');
 const seg=picked.slice(part*PER,(part+1)*PER);
 let d='',dFull='',pTotal=0,tTotal=0;
 plist.innerHTML='';
 picked.forEach((id,i)=>{{
  const p=centers[id]; if(!p)return;
  dFull+=(dFull? ' L ':'M ')+p[0]+' '+p[1];
  tTotal+=costOf(id).num;
 }});
 seg.forEach((id,i)=>{{
  const p=centers[id]; if(!p)return;
  d+=(i? ' L ':'M ')+p[0]+' '+p[1];
  const c=costOf(id);
  const li=document.createElement('li');
  li.innerHTML='<span class="n">'+(i+1)+'</span><span>'+c.name+' — '+c.costTxt+'</span>';
  plist.appendChild(li);
  pTotal+=c.num;
 }});
 route.setAttribute('d',d);
 fullEl.setAttribute('d',dFull);
 badgeLayer.innerHTML='';
 seg.forEach((id,i)=>{{
  const p=centers[id]; if(!p)return;
  const c=document.createElementNS('http://www.w3.org/2000/svg','circle');
  c.setAttribute('cx',p[0]);c.setAttribute('cy',p[1]);c.setAttribute('r',14);c.setAttribute('class','ringbadge');
  const t=document.createElementNS('http://www.w3.org/2000/svg','text');
  t.setAttribute('x',p[0]);t.setAttribute('y',p[1]+5);t.setAttribute('class','stepnum');t.textContent=i+1;
  badgeLayer.appendChild(c);badgeLayer.appendChild(t);
 }});
 ptotal.innerHTML='Parte: <b>'+pTotal.toLocaleString('pt-PT')+'</b> ouro · Rota total: <b>'+tTotal.toLocaleString('pt-PT')+'</b> ouro';
}}
document.getElementById('pclear').addEventListener('click',()=>{{picked=[];part=0;render();}});
function apply(){{mv.style.transform=`translate(${{tx}}px,${{ty}}px) scale(${{scale}})`;}}
vp.addEventListener('wheel',e=>{{e.preventDefault();const f=e.deltaY<0?1.15:1/1.15;
 const r=vp.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;
 tx=mx-(mx-tx)*f; ty=my-(my-ty)*f; scale*=f; apply();}},{{passive:false}});
vp.addEventListener('mousedown',e=>{{drag={{x:e.clientX,y:e.clientY,tx,ty}};vp.classList.add('drag');}});
window.addEventListener('mousemove',e=>{{if(!drag)return;if(Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y)>3)moved=true;tx=drag.tx+e.clientX-drag.x;ty=drag.ty+e.clientY-drag.y;apply();}});
window.addEventListener('mouseup',()=>{{drag=null;vp.classList.remove('drag');}});
apply();render();
</script>
</body></html>"""

    out = os.path.join(ROOT, "mapa_runas.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)
    print("OK:", out, f"({len(nodes)} nos)")
    if missing_icons:
        print("sem icone:", missing_icons)
    try:
        os.startfile(out)
    except Exception:
        pass


def esc_html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


if __name__ == "__main__":
    main()
