# NPC Brain — benchmark LLM sur grille

Un agent (LLM + module algorithmique) évolue sur une grille pour ramasser des pièces
d'or en évitant les ennemis. Le projet instrumente les runs en architecture médaillon
(bronze / silver / gold) pour comparer les configurations (modèle, format de prompt,
etc.) via des KPI calculés avec dbt-duckdb.

## Prérequis

- Python 3.13 (le venv `.venv/` est déjà présent à la racine)
- [LM Studio](https://lmstudio.ai/) lancé en local avec un modèle chargé, serveur API
  compatible OpenAI démarré (`/v1/chat/completions`)
- Un fichier `projet/.env` avec :
  ```
  LLM_API_URL=http://localhost:<port>/v1
  LLM_API_TOKEN=<un token quelconque, LM Studio ne le vérifie pas>
  ```

## Installation

```bash
# depuis la racine du repo
./.venv/Scripts/pip install -r requirements.txt
```

## 1. Lancer un run (bronze)

1. Démarrer LM Studio et charger le modèle voulu (vérifier que son nom correspond à
   la variable `MODEL` dans `projet/npc_brain.ipynb`, et l'ajouter à
   `MODEL_PARAM_COUNTS` si besoin).
2. Ouvrir `projet/npc_brain.ipynb` et exécuter les cellules jusqu'à la dernière, qui
   appelle `game_loop(world_map=initial_map, max_turns=10, config=default_config)`.
3. Pour tester une autre configuration (température, historique désactivé,
   priorisation implicite...), modifier `default_config = RunConfig(...)` dans la
   dernière cellule avant de relancer.
4. Chaque run écrit deux fichiers parquet :
   `data/bronze/steps/run_{timestamp}_{config_id}.parquet` et
   `data/bronze/runs/run_{timestamp}_{config_id}.parquet`.
5. Répéter pour accumuler plusieurs runs / configurations avant de passer à l'étape
   suivante (le flow n'est pas temps réel : on traite les runs par batch).

⚠️ Si tu modifies `npc_brain.ipynb`, resynchronise le miroir `.py` avec :

```bash
./.venv/Scripts/jupytext --to py:percent projet/npc_brain.ipynb -o projet/npc_brain.py
```

(ne pas utiliser `jupytext --sync`, qui peut réordonner/corrompre les cellules sur ce
notebook — l'export à sens unique ipynb → py est la méthode sûre.)

## 2. Nettoyage (silver)

```bash
./.venv/Scripts/python pipeline/silver_transform.py
```

Lit tous les parquets de `data/bronze/`, type les colonnes, gère les valeurs
manquantes explicitement, déduplique par `run_id` / `(run_id, step_index)`, et écrit
`data/silver/runs.parquet` + `data/silver/steps.parquet`.

## 3. Agrégats KPI (gold)

```bash
cd dbt/npc_benchmark
../.venv/Scripts/dbt run --profiles-dir .
../.venv/Scripts/dbt test --profiles-dir .   # optionnel : vérifie unicité/not-null de run_id
```

Génère `data/gold/benchmark.duckdb`, avec un modèle par KPI (`kpi_steps_per_coin`,
`kpi_success_rate`, `kpi_efficiency_score`, etc. — voir
`dbt/npc_benchmark/models/marts/schema.yml` pour la description de chacun).

## 4. Consulter les résultats

```bash
./.venv/Scripts/python -c "
import duckdb
con = duckdb.connect('data/gold/benchmark.duckdb', read_only=True)
print(con.execute('select * from kpi_efficiency_score').df())
"
```

(ou n'importe quel client DuckDB / futur outil de dataviz pointant sur ce fichier.)

## Cycle complet résumé

```
LM Studio lancé
   │
   ▼
npc_brain.ipynb (plusieurs runs/configs)  →  data/bronze/{steps,runs}/*.parquet
   │
   ▼
python pipeline/silver_transform.py       →  data/silver/{steps,runs}.parquet
   │
   ▼
dbt run (depuis dbt/npc_benchmark/)       →  data/gold/benchmark.duckdb (KPI par config)
```
