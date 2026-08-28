# Méthode — décomposition Prix / Volume / Mix

Méthode standard de contrôle de gestion (sales variance analysis) pour expliquer
un écart de chiffre d'affaires entre Budget et Réel, catégorie par catégorie
puis département par département.

## Notations (pour une catégorie, sur une période)

- `AQ` / `BQ` : quantité réelle / budgétée
- `AP` / `BP` : prix moyen réel / budgété
- `AR = AQ x AP` : chiffre d'affaires réel — `BR = BQ x BP` : budgété

## 1. Écart Prix et Écart Volume (niveau catégorie)

```
Écart Prix   = (AP - BP) x AQ
Écart Volume = (AQ - BQ) x BP
```

Identité exacte (pas une approximation) :

```
Écart Prix + Écart Volume
  = AP.AQ - BP.AQ + AQ.BP - BQ.BP
  = AP.AQ - BQ.BP
  = AR - BR
  = Écart total
```

## 2. Écart Mix (niveau département, plusieurs catégories i)

L'écart Volume brut mélange deux effets : le département a-t-il vendu plus/moins
en tonnage global (**volume pur**), et a-t-il vendu une répartition différente
entre ses catégories (**mix**, ex. plus de catégories bon marché) ? On les sépare
avec le prix moyen pondéré budgété du département `BWAP = Σ(BQi·BPi) / ΣBQi` :

```
Écart Volume (dépt) = (ΣAQi - ΣBQi) x BWAP
Écart Mix (dépt)     = Σi [ (AQi - ΣAQi x BQi/ΣBQi) x BPi ]
```

`(AQi - ΣAQi × BQi/ΣBQi)` compare la quantité réelle de la catégorie i à ce
qu'elle aurait dû être si le département avait gardé exactement le mix
budgété — valorisé au prix budgété de la catégorie.

Identité exacte : `Écart Volume (dépt) + Écart Mix (dépt) = Σi Écart Volume (catégorie i)`.
Combinée à l'identité prix/volume ci-dessus :

```
Écart Prix (dépt) + Écart Volume (dépt) + Écart Mix (dépt) = Écart total (dépt)
```

## Vérification

Les deux identités sont vérifiées par des `assert` dans
[`src/variance_report.py`](../src/variance_report.py) (fonctions `decompose` et
`aggregate`) : si un écart d'arrondi dépasse 0,01 €, le script s'arrête au lieu
de produire un chiffre faux.
