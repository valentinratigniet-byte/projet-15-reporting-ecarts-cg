"""
Reporting de gestion : compare Budget vs Réel par catégorie/département et
décompose l'écart en 3 effets (méthode standard du contrôle de gestion) :

  Écart total = Écart Prix + Écart Volume + Écart Mix

  - Écart Prix   = (Prix réel - Prix budget) x Qté réelle
  - Écart Volume = (Qté totale réelle - Qté totale budget) x Prix moyen budgété du département
  - Écart Mix    = ce qui reste : la répartition des ventes entre catégories
                    a dévié du mix budgété (ex : on a vendu plus de catégories
                    moins chères que prévu, même à quantité totale égale).

Le détail (formules, preuve de l'identité) est dans docs/methode.md.

Sortie : output/reporting_ecarts_<AAAA-MM>.xlsx + commentaires en console.
Usage : python src/variance_report.py
"""
import os
from collections import defaultdict
from datetime import date
from pathlib import Path

import psycopg2
from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

DSN = os.environ.get("DATABASE_URL",
                      "postgresql://portfolio:portfolio@127.0.0.1:5433/ecommerce")
OUT = Path(__file__).resolve().parent.parent / "output"
EPS = 0.01  # tolérance d'arrondi sur l'identité prix+volume+mix = total

# Regroupement métier des 10 catégories du Projet 07 en 4 départements.
DEPARTMENTS = {
    "Électronique": "Tech & Loisirs numériques",
    "Informatique": "Tech & Loisirs numériques",
    "Jouets": "Tech & Loisirs numériques",
    "Maison": "Maison & Quotidien",
    "Jardin": "Maison & Quotidien",
    "Alimentation": "Maison & Quotidien",
    "Mode": "Mode & Bien-être",
    "Beauté": "Mode & Bien-être",
    "Sport": "Mode & Bien-être",
    "Livres": "Culture",
}

PETROL = "137A8B"; PETROL_D = "0C5563"; AMBRE = "E4A93C"
GREEN = "2FA36B"; RED = "D9534F"
EURO = '#,##0" €"'
thin = Side(style="thin", color="DCE2E8")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
HEAD_FILL = PatternFill("solid", fgColor=PETROL)
HEAD_FONT = Font(bold=True, color="FFFFFF")


def header_row(ws, row, headers, start=1):
    for i, h in enumerate(headers):
        c = ws.cell(row=row, column=start + i, value=h)
        c.fill = HEAD_FILL; c.font = HEAD_FONT; c.border = BORDER
        c.alignment = Alignment(horizontal="center")


def fetch_rows(cur):
    """Réel et Budget par (catégorie, mois), joints en Python."""
    cur.execute("""
        SELECT c.id, c.name, date_trunc('month', o.order_date)::date AS month,
               sum(oi.quantity) AS qty, sum(oi.quantity * oi.unit_price) AS revenue
        FROM order_item oi
        JOIN orders o ON o.id = oi.order_id
        JOIN product pr ON pr.id = oi.product_id
        JOIN category c ON c.id = pr.category_id
        WHERE date_trunc('month', o.order_date) < date_trunc('month', now())
        GROUP BY 1, 2, 3
    """)
    actual = {(cid, month): (name, float(qty), float(rev))
              for cid, name, month, qty, rev in cur.fetchall()}

    cur.execute("SELECT category_id, month, budget_qty, budget_unit_price FROM budget_category_month")
    budget = {(cid, month): (float(bq), float(bp)) for cid, month, bq, bp in cur.fetchall()}

    rows = []
    for key, (name, aq, ar) in actual.items():
        bq, bp = budget[key]
        rows.append({"category": name, "dept": DEPARTMENTS[name], "month": key[1],
                     "aq": aq, "ar": ar, "bq": bq, "bp": bp})
    return rows


def decompose(rows):
    """Écart prix/volume par ligne (catégorie x mois), puis écart mix par département x mois."""
    for r in rows:
        ap = r["ar"] / r["aq"]
        br = r["bq"] * r["bp"]
        r["ap"], r["br"] = ap, br
        r["price_var"] = (ap - r["bp"]) * r["aq"]
        r["volume_var"] = (r["aq"] - r["bq"]) * r["bp"]
        r["total_var"] = r["ar"] - br
        assert abs(r["price_var"] + r["volume_var"] - r["total_var"]) < EPS, \
            f"Identité prix+volume=total cassée pour {r['category']} {r['month']}"

    # Écart mix : par département x mois, on retire l'effet volume "pur" de l'effet volume brut.
    by_dept_month = defaultdict(list)
    for r in rows:
        by_dept_month[(r["dept"], r["month"])].append(r)

    mix_var = defaultdict(float)      # dept -> somme des écarts mix
    dept_volume_var = defaultdict(float)
    for (dept, month), group in by_dept_month.items():
        aq_dept = sum(g["aq"] for g in group)
        bq_dept = sum(g["bq"] for g in group)
        bwap = sum(g["bq"] * g["bp"] for g in group) / bq_dept  # prix moyen pondéré budgété
        vol_dept_month = (aq_dept - bq_dept) * bwap
        dept_volume_var[dept] += vol_dept_month
        for g in group:
            expected_qty = aq_dept * (g["bq"] / bq_dept)
            mix_var[dept] += (g["aq"] - expected_qty) * g["bp"]

    return mix_var, dept_volume_var


def aggregate(rows, mix_var, dept_volume_var):
    cat = defaultdict(lambda: {"ar": 0.0, "br": 0.0, "price_var": 0.0, "volume_var": 0.0, "dept": None})
    for r in rows:
        c = cat[r["category"]]
        c["dept"] = r["dept"]
        c["ar"] += r["ar"]; c["br"] += r["br"]
        c["price_var"] += r["price_var"]; c["volume_var"] += r["volume_var"]

    dept = defaultdict(lambda: {"ar": 0.0, "br": 0.0, "price_var": 0.0})
    for name, c in cat.items():
        d = dept[c["dept"]]
        d["ar"] += c["ar"]; d["br"] += c["br"]; d["price_var"] += c["price_var"]
    for d_name, d in dept.items():
        d["volume_var"] = dept_volume_var[d_name]
        d["mix_var"] = mix_var[d_name]
        d["total_var"] = d["ar"] - d["br"]
        assert abs(d["price_var"] + d["volume_var"] + d["mix_var"] - d["total_var"]) < EPS, \
            f"Identité prix+volume+mix=total cassée pour {d_name}"
    return cat, dept


def comment(dept_name, d):
    effects = {"volume": d["volume_var"], "mix": d["mix_var"], "prix": d["price_var"]}
    driver = max(effects, key=lambda k: abs(effects[k]))
    sens = "favorable" if d["total_var"] >= 0 else "défavorable"
    explain = {
        "volume": "le volume total vendu s'écarte du budget",
        "mix": "le mix de ventes a dévié du budget (déplacement entre catégories à prix différents, à volume total quasi stable)",
        "prix": "le prix de vente réalisé s'écarte du prix budgété",
    }[driver]
    return (f"{dept_name} : écart {sens} de {d['total_var']:+,.0f} €. "
            f"Facteur principal : {driver} ({effects[driver]:+,.0f} €) — {explain}.")


def build_excel(cat, dept, comments, path):
    wb = Workbook()

    ws = wb.active; ws.title = "Synthèse"; ws.sheet_view.showGridLines = False
    ws["B2"] = "Reporting de gestion — écarts Budget vs Réel"
    ws["B2"].font = Font(bold=True, size=18, color=PETROL_D)
    ws["B3"] = f"Généré automatiquement le {date.today().isoformat()}"
    ws["B3"].font = Font(italic=True, color="5E6B7A")

    total_ar = sum(d["ar"] for d in dept.values())
    total_br = sum(d["br"] for d in dept.values())
    total_var = total_ar - total_br
    cards = [("Réel", total_ar, EURO), ("Budget", total_br, EURO),
             ("Écart total", total_var, '+#,##0" €";-#,##0" €"'),
             ("Écart %", total_var / total_br, '+0.0%;-0.0%')]
    for i, (label, val, fmt) in enumerate(cards):
        col = 2 + i * 2
        lc = ws.cell(row=5, column=col, value=label)
        lc.font = Font(bold=True, color="5E6B7A", size=9)
        vc = ws.cell(row=6, column=col, value=val)
        vc.font = Font(bold=True, size=16, color=(GREEN if val >= 0 or fmt.startswith("#") else RED)
                        if label.startswith("Écart") else PETROL)
        vc.number_format = fmt
        ws.merge_cells(start_row=5, start_column=col, end_row=5, end_column=col + 1)
        ws.merge_cells(start_row=6, start_column=col, end_row=6, end_column=col + 1)
    for col in range(2, 10):
        ws.column_dimensions[get_column_letter(col)].width = 15

    ws_d = wb.create_sheet("Écarts par département"); ws_d.sheet_view.showGridLines = False
    header_row(ws_d, 1, ["Département", "Budget €", "Réel €", "Écart total €",
                          "dont Volume €", "dont Mix €", "dont Prix €"])
    depts_sorted = sorted(dept.items(), key=lambda kv: kv[0])
    for r, (name, d) in enumerate(depts_sorted, start=2):
        ws_d.cell(row=r, column=1, value=name).border = BORDER
        for col, key in [(2, "br"), (3, "ar"), (4, "total_var"), (5, "volume_var"), (6, "mix_var"), (7, "price_var")]:
            c = ws_d.cell(row=r, column=col, value=round(d[key])); c.number_format = EURO; c.border = BORDER
    ws_d.column_dimensions["A"].width = 26
    for col in "BCDEFG":
        ws_d.column_dimensions[col].width = 15
    bar = BarChart(); bar.title = "Écart total par département"; bar.height = 8; bar.width = 18; bar.legend = None
    data = Reference(ws_d, min_col=4, min_row=1, max_row=len(depts_sorted) + 1)
    cats = Reference(ws_d, min_col=1, min_row=2, max_row=len(depts_sorted) + 1)
    bar.add_data(data, titles_from_data=True); bar.set_categories(cats)
    bar.series[0].graphicalProperties.solidFill = PETROL
    ws_d.add_chart(bar, "B10")

    ws_c = wb.create_sheet("Écarts par catégorie"); ws_c.sheet_view.showGridLines = False
    header_row(ws_c, 1, ["Catégorie", "Département", "Budget €", "Réel €",
                          "Écart total €", "dont Volume €", "dont Prix €"])
    cats_sorted = sorted(cat.items(), key=lambda kv: abs(kv[1]["ar"] - kv[1]["br"]), reverse=True)
    for r, (name, c) in enumerate(cats_sorted, start=2):
        ws_c.cell(row=r, column=1, value=name).border = BORDER
        ws_c.cell(row=r, column=2, value=c["dept"]).border = BORDER
        total = c["ar"] - c["br"]
        for col, val in [(3, c["br"]), (4, c["ar"]), (5, total), (6, c["volume_var"]), (7, c["price_var"])]:
            cell = ws_c.cell(row=r, column=col, value=round(val)); cell.number_format = EURO; cell.border = BORDER
    ws_c.column_dimensions["A"].width = 16; ws_c.column_dimensions["B"].width = 24
    for col in "CDEFG":
        ws_c.column_dimensions[col].width = 14
    ws_c.conditional_formatting.add(
        f"E2:E{len(cats_sorted)+1}",
        ColorScaleRule(start_type="min", start_color=RED, mid_type="num", mid_value=0, mid_color="FFFFFF",
                        end_type="max", end_color=GREEN))

    ws_n = wb.create_sheet("Commentaires"); ws_n.sheet_view.showGridLines = False
    ws_n["B2"] = "Commentaires par département (générés automatiquement)"
    ws_n["B2"].font = Font(bold=True, size=13, color=PETROL_D)
    for i, line in enumerate(comments, start=4):
        ws_n.cell(row=i, column=2, value=line).alignment = Alignment(wrap_text=True)
        ws_n.row_dimensions[i].height = 30
    ws_n.column_dimensions["B"].width = 110

    wb.save(path)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    conn = psycopg2.connect(DSN); cur = conn.cursor()
    rows = fetch_rows(cur)
    cur.close(); conn.close()

    if not rows:
        raise SystemExit("Aucune donnée : lancer generate_budget.py après avoir seedé le Projet 07.")

    mix_var, dept_volume_var = decompose(rows)
    cat, dept = aggregate(rows, mix_var, dept_volume_var)
    comments = [comment(name, d) for name, d in sorted(dept.items(), key=lambda kv: kv[1]["total_var"])]

    path = OUT / f"reporting_ecarts_{date.today().isoformat()}.xlsx"
    build_excel(cat, dept, comments, path)

    total_var = sum(d["total_var"] for d in dept.values())
    print(f"Rapport généré : {path.name}")
    print(f"  Écart total : {total_var:+,.0f} € sur {len(dept)} départements, {len(cat)} catégories.")
    for line in comments:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
