"""
Generate index.html — a self-contained, mobile-friendly dashboard for
browsing scraped Chiswick lots, sold comps, and flagged deals.

No server needed: this produces one static HTML file with the data embedded
directly in it. Host it anywhere (GitHub Pages, Netlify Drop, etc.) to view
it on your phone from anywhere.

Usage:
    python generate_dashboard.py
"""

import json
import sqlite3
import statistics
from datetime import datetime, timezone

from analyze import extract_type, extract_size_m2, TYPE_KEYWORDS

DB_PATH = "chiswick_rugs.db"
OUT_PATH = "index.html"
DEAL_THRESHOLD = 0.6  # same heuristic as analyze.py


def load_lots():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM lots").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def build_dataset(rows):
    sold_by_type = {}
    lots = []

    for r in rows:
        rug_type = extract_type(r["title"] or "")
        size_m2 = extract_size_m2(r["title"] or "")
        r["type"] = rug_type
        r["size_m2"] = size_m2
        if r.get("is_sold") and r.get("sold_price_gbp"):
            sold_by_type.setdefault(rug_type, []).append(r["sold_price_gbp"])

    comps = {t: statistics.median(prices) for t, prices in sold_by_type.items()}

    for r in rows:
        is_deal = False
        comp_median = comps.get(r["type"])
        if (not r.get("is_sold")) and r.get("estimate_high_gbp") and comp_median:
            is_deal = r["estimate_high_gbp"] < comp_median * DEAL_THRESHOLD

        lots.append({
            "url": r["lot_url"],
            "title": r["title"],
            "type": r["type"],
            "size_m2": r["size_m2"],
            "is_sold": bool(r.get("is_sold")),
            "sold_price": r.get("sold_price_gbp"),
            "est_low": r.get("estimate_low_gbp"),
            "est_high": r.get("estimate_high_gbp"),
            "condition": r.get("condition_rating"),
            "image": r.get("image_url"),
            "is_deal": is_deal,
            "comp_median": comp_median,
        })

    return lots, comps


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rug &amp; Carpet Comps — Chiswick Auctions</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #1C1917;
    --bg-alt: #262220;
    --bg-card: #29241F;
    --text: #EDE6D6;
    --muted: #9C8F80;
    --border: rgba(237,230,214,0.10);
    --red: #B33F2E;
    --indigo: #3F5C7A;
    --ochre: #D4A13D;
    --green: #5B7B5A;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: 'IBM Plex Sans', sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .zigzag {
    height: 6px;
    width: 100%;
    background-image:
      linear-gradient(135deg, var(--red) 25%, transparent 25%),
      linear-gradient(225deg, var(--red) 25%, transparent 25%),
      linear-gradient(45deg, var(--ochre) 25%, transparent 25%),
      linear-gradient(315deg, var(--ochre) 25%, transparent 25%);
    background-position: 0 0, 6px 0, 6px -6px, 0px 6px;
    background-size: 12px 12px;
    background-repeat: repeat-x;
    opacity: 0.85;
  }
  header {
    padding: 28px 20px 20px;
    background: var(--bg-alt);
  }
  header h1 {
    font-family: 'Fraunces', serif;
    font-optical-sizing: auto;
    font-weight: 600;
    font-size: 1.7rem;
    margin: 0 0 4px;
    letter-spacing: -0.01em;
  }
  header .sub {
    color: var(--muted);
    font-size: 0.85rem;
  }
  .stats {
    display: flex;
    gap: 10px;
    padding: 16px 20px;
    overflow-x: auto;
  }
  .stat {
    flex: 1 0 auto;
    min-width: 92px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 10px 12px;
    text-align: center;
  }
  .stat .n {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.25rem;
    font-weight: 600;
  }
  .stat .l {
    font-size: 0.68rem;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .controls {
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--bg);
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
  }
  .controls input[type="search"] {
    width: 100%;
    padding: 10px 12px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.95rem;
  }
  .chips {
    display: flex;
    gap: 8px;
    margin-top: 10px;
    flex-wrap: wrap;
  }
  .chip {
    padding: 6px 12px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--bg-card);
    color: var(--muted);
    font-size: 0.78rem;
    cursor: pointer;
    user-select: none;
  }
  .chip.active {
    background: var(--indigo);
    color: var(--text);
    border-color: var(--indigo);
  }
  select#typeFilter {
    margin-top: 10px;
    width: 100%;
    padding: 9px 12px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-family: 'IBM Plex Sans', sans-serif;
    font-size: 0.9rem;
  }
  #list {
    padding: 14px 20px 60px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    display: flex;
    gap: 12px;
    padding: 12px;
    position: relative;
    text-decoration: none;
    color: var(--text);
  }
  .card.deal {
    border-left: 3px solid var(--red);
  }
  .card img {
    width: 72px;
    height: 72px;
    object-fit: cover;
    border-radius: 8px;
    flex-shrink: 0;
    background: var(--bg-alt);
  }
  .card .swatch {
    width: 72px;
    height: 72px;
    border-radius: 8px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: 'Fraunces', serif;
    font-size: 1.4rem;
    color: rgba(0,0,0,0.35);
  }
  .card .body {
    flex: 1;
    min-width: 0;
  }
  .card .title {
    font-size: 0.9rem;
    font-weight: 500;
    line-height: 1.3;
    margin-bottom: 6px;
  }
  .card .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }
  .badge {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    padding: 2px 7px;
    border-radius: 5px;
    font-weight: 600;
  }
  .badge.sold { background: var(--indigo); color: var(--text); }
  .badge.active { background: var(--ochre); color: #1C1917; }
  .badge.deal { background: var(--red); color: var(--text); }
  .price {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.85rem;
    color: var(--text);
  }
  .comp {
    font-size: 0.72rem;
    color: var(--muted);
    margin-top: 4px;
  }
  .empty {
    text-align: center;
    color: var(--muted);
    padding: 60px 20px;
    font-size: 0.9rem;
  }
  footer {
    text-align: center;
    color: var(--muted);
    font-size: 0.72rem;
    padding: 20px;
  }
</style>
</head>
<body>

<header>
  <h1>Rug &amp; Carpet Comps</h1>
  <div class="sub">Chiswick Auctions · last updated GENERATED_AT</div>
</header>
<div class="zigzag"></div>

<div class="stats">
  <div class="stat"><div class="n">STAT_SOLD</div><div class="l">Sold comps</div></div>
  <div class="stat"><div class="n">STAT_ACTIVE</div><div class="l">Active lots</div></div>
  <div class="stat"><div class="n">STAT_DEALS</div><div class="l">Flagged deals</div></div>
  <div class="stat"><div class="n">STAT_TYPES</div><div class="l">Rug types</div></div>
</div>

<div class="controls">
  <input type="search" id="searchBox" placeholder="Search titles (e.g. Tabriz, Kilim, Kazak)...">
  <div class="chips">
    <div class="chip active" data-filter="all">All</div>
    <div class="chip" data-filter="deal">Deals</div>
    <div class="chip" data-filter="sold">Sold</div>
    <div class="chip" data-filter="active">Active</div>
  </div>
  <select id="typeFilter">
    <option value="">All types</option>
  </select>
</div>

<div id="list"></div>
<div class="empty" id="emptyMsg" style="display:none;">No lots match your filters.</div>

<footer>Data scraped from chiswickauctions.co.uk for personal research use.</footer>

<script>
const LOTS = LOTS_JSON;

const listEl = document.getElementById('list');
const searchBox = document.getElementById('searchBox');
const typeFilter = document.getElementById('typeFilter');
const emptyMsg = document.getElementById('emptyMsg');
let activeChip = 'all';

// Populate type dropdown
const types = [...new Set(LOTS.map(l => l.type))].sort();
types.forEach(t => {
  const opt = document.createElement('option');
  opt.value = t;
  opt.textContent = t;
  typeFilter.appendChild(opt);
});

function gbp(n) {
  if (n === null || n === undefined) return '';
  return '£' + Math.round(n).toLocaleString();
}

function swatchColor(type) {
  let hash = 0;
  for (let i = 0; i < type.length; i++) hash = type.charCodeAt(i) + ((hash << 5) - hash);
  const hues = ['#B33F2E', '#3F5C7A', '#D4A13D', '#5B7B5A', '#8C5E8C'];
  return hues[Math.abs(hash) % hues.length];
}

function render() {
  const q = searchBox.value.trim().toLowerCase();
  const t = typeFilter.value;

  const filtered = LOTS.filter(l => {
    if (q && !l.title.toLowerCase().includes(q)) return false;
    if (t && l.type !== t) return false;
    if (activeChip === 'deal' && !l.is_deal) return false;
    if (activeChip === 'sold' && !l.is_sold) return false;
    if (activeChip === 'active' && l.is_sold) return false;
    return true;
  });

  listEl.innerHTML = '';
  emptyMsg.style.display = filtered.length ? 'none' : 'block';

  filtered.forEach(l => {
    const card = document.createElement('a');
    card.href = l.url;
    card.target = '_blank';
    card.rel = 'noopener';
    card.className = 'card' + (l.is_deal ? ' deal' : '');

    let thumb;
    if (l.image) {
      thumb = `<img src="${l.image}" alt="">`;
    } else {
      thumb = `<div class="swatch" style="background:${swatchColor(l.type)}">${l.type.charAt(0)}</div>`;
    }

    let badges = '';
    if (l.is_sold) badges += '<span class="badge sold">Sold</span>';
    else badges += '<span class="badge active">Active</span>';
    if (l.is_deal) badges += '<span class="badge deal">Deal</span>';
    if (l.condition) badges += `<span class="badge" style="background:transparent;color:var(--muted);border:1px solid var(--border)">Cond. ${l.condition}</span>`;

    let priceLine;
    if (l.is_sold) {
      priceLine = `<span class="price">${gbp(l.sold_price)}</span>`;
    } else {
      priceLine = `<span class="price">${gbp(l.est_low)}–${gbp(l.est_high)}</span>`;
    }

    let compLine = '';
    if (!l.is_sold && l.comp_median) {
      compLine = `<div class="comp">Comp median (${l.type}): ${gbp(l.comp_median)}</div>`;
    }

    card.innerHTML = `
      ${thumb}
      <div class="body">
        <div class="title">${l.title}</div>
        <div class="meta">${badges} ${priceLine}</div>
        ${compLine}
      </div>
    `;
    listEl.appendChild(card);
  });
}

document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    activeChip = chip.dataset.filter;
    render();
  });
});

searchBox.addEventListener('input', render);
typeFilter.addEventListener('change', render);

render();
</script>
</body>
</html>
"""


def main():
    rows = load_lots()
    if not rows:
        print("No data found — run scraper.py first.")
        return

    lots, comps = build_dataset(rows)

    n_sold = sum(1 for l in lots if l["is_sold"])
    n_active = sum(1 for l in lots if not l["is_sold"])
    n_deals = sum(1 for l in lots if l["is_deal"])
    n_types = len(set(l["type"] for l in lots))

    generated_at = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    html = HTML_TEMPLATE
    html = html.replace("LOTS_JSON", json.dumps(lots))
    html = html.replace("GENERATED_AT", generated_at)
    html = html.replace("STAT_SOLD", str(n_sold))
    html = html.replace("STAT_ACTIVE", str(n_active))
    html = html.replace("STAT_DEALS", str(n_deals))
    html = html.replace("STAT_TYPES", str(n_types))

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote {OUT_PATH} ({len(lots)} lots, {n_deals} flagged deals).")


if __name__ == "__main__":
    main()
