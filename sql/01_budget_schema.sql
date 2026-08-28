-- =====================================================================
-- Projet 15 — Reporting de gestion : table Budget
-- Ajoutée à la base du Projet 07 (ecommerce). Un budget qté/prix par
-- catégorie et par mois, comparé ensuite au réalisé (order_item/orders).
-- =====================================================================

CREATE TABLE IF NOT EXISTS budget_category_month (
    category_id       INT           NOT NULL REFERENCES category(id),
    month              DATE          NOT NULL,   -- 1er du mois
    budget_qty         INT           NOT NULL CHECK (budget_qty >= 0),
    budget_unit_price  NUMERIC(10,2) NOT NULL CHECK (budget_unit_price > 0),
    PRIMARY KEY (category_id, month)
);
