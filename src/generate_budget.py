"""
Génère le Budget (qté + prix unitaire, par catégorie et par mois) et le charge
dans `budget_category_month`. Le Réel existe déjà (base du Projet 07) — le
budget est ici la seule donnée manquante pour faire un vrai reporting d'écarts.

Simulation réaliste : chaque catégorie reçoit un biais de prévision fixe
(certaines sur-estimées, d'autres sous-estimées, un peu de bruit mensuel) au
lieu d'un budget parfaitement calé sur le réel — sinon l'écart serait
toujours nul, ce qui n'a aucun intérêt pédagogique.

Usage : python src/generate_budget.py
"""
import os
import random
from datetime import date

import psycopg2

DSN = os.environ.get("DATABASE_URL",
                      "postgresql://portfolio:portfolio@127.0.0.1:5433/ecommerce")


def main() -> None:
    conn = psycopg2.connect(DSN)
    cur = conn.cursor()

    # Réel par catégorie x mois (mois en cours exclu : encore incomplet).
    cur.execute("""
        SELECT c.id, date_trunc('month', o.order_date)::date AS month,
               sum(oi.quantity) AS qty,
               sum(oi.quantity * oi.unit_price) / sum(oi.quantity) AS avg_price
        FROM order_item oi
        JOIN orders o ON o.id = oi.order_id
        JOIN product pr ON pr.id = oi.product_id
        JOIN category c ON c.id = pr.category_id
        WHERE date_trunc('month', o.order_date) < date_trunc('month', now())
        GROUP BY 1, 2
    """)
    actuals = cur.fetchall()

    cur.execute("SELECT id FROM category")
    category_ids = [r[0] for r in cur.fetchall()]

    # Biais de prévision par catégorie, fixe et reproductible (seed = id).
    bias = {}
    for cid in category_ids:
        rng = random.Random(cid)
        bias[cid] = {
            "qty": rng.uniform(-0.12, 0.15),     # volume sur/sous-budgété
            "price": rng.uniform(-0.06, 0.06),   # prix sur/sous-budgété
        }

    rng_noise = random.Random(42)
    rows = []
    for cid, month, qty, avg_price in actuals:
        b = bias[cid]
        qty_noise = rng_noise.gauss(0, 0.03)
        price_noise = rng_noise.gauss(0, 0.015)
        budget_qty = max(1, round(float(qty) * (1 + b["qty"] + qty_noise)))
        budget_price = round(float(avg_price) * (1 + b["price"] + price_noise), 2)
        rows.append((cid, month, budget_qty, budget_price))

    cur.execute("TRUNCATE budget_category_month")
    cur.executemany("""
        INSERT INTO budget_category_month (category_id, month, budget_qty, budget_unit_price)
        VALUES (%s, %s, %s, %s)
    """, rows)
    conn.commit()
    cur.close()
    conn.close()
    print(f"Budget généré : {len(rows)} lignes catégorie x mois "
          f"({len(category_ids)} catégories, jusqu'à {date.today().isoformat()}).")


if __name__ == "__main__":
    main()
