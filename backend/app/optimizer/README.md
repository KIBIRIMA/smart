# Moteur d'optimisation — zone protégée

⚠️ **Règle d'architecture stricte** : le moteur `tournee_optimizer_v12.py` n'est
**JAMAIS modifié directement**. Toute intégration passe par `adapter.py`.

## Fichiers à déposer ici (depuis le repo Streamlit existant)

Copier **tels quels**, sans aucune modification :

- `tournee_optimizer_v12.py`  ← moteur principal (OR-Tools VRP + Bin-Packing 2D FFD + Fuzzy Matching)
- `tournee_optimizer_v11.py`  ← fallback
- `tournee_optimizer_v10.py`  ← fallback
- `tournee_optimizer_v9.py`   ← fallback
- `tournee_optimizer_v8.py`   ← fallback
- `machines.json`             ← catalogue 76+ modèles (dimensions réelles)

## Comment c'est appelé

```
adapter.run_optimization(missions, vehicules, depot, params)
  → engine_loader.load_engine()  charge v12, retombe sur v11→v10→v9→v8 si import/exécution échoue
  → engine.optimize(...)         appelle le moteur TEL QUEL
  → adapter mappe la sortie vers le schéma OptimizeResult + génère les explications
```

Tant que les vrais fichiers ne sont pas déposés, `engine_loader` utilise
`_reference_engine.py` (implémentation de référence) pour que l'API tourne
en bout-en-bout. Dès que `tournee_optimizer_v12.py` est présent, il est
automatiquement préféré.
