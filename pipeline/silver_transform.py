"""
Bronze -> Silver : charge tous les parquets bronze (steps + runs), nettoie, déduplique,
écrit deux tables silver propres et jointes sur run_id.

Usage : python pipeline/silver_transform.py
"""

from pathlib import Path

import duckdb

BASE_DIR = Path(__file__).resolve().parent.parent
BRONZE_STEPS_GLOB = str(BASE_DIR / "data" / "bronze" / "steps" / "*.parquet")
BRONZE_RUNS_GLOB = str(BASE_DIR / "data" / "bronze" / "runs" / "*.parquet")
SILVER_DIR = BASE_DIR / "data" / "silver"
SILVER_DIR.mkdir(parents=True, exist_ok=True)


def clean_runs(con: duckdb.DuckDBPyConnection) -> None:
    raw_count = con.execute(f"SELECT count(*) FROM read_parquet('{BRONZE_RUNS_GLOB}', union_by_name=True)").fetchone()[0]

    con.execute(f"""
        CREATE OR REPLACE TABLE runs_clean AS
        WITH raw AS (
            SELECT * FROM read_parquet('{BRONZE_RUNS_GLOB}', union_by_name=True)
        ),
        -- champs sans lesquels une ligne "run" est inexploitable : on l'exclut explicitement (pas un silent drop)
        valid AS (
            SELECT *
            FROM raw
            WHERE run_id IS NOT NULL
              AND config_id IS NOT NULL
              AND timestamp IS NOT NULL
              AND nb_pieces_totales IS NOT NULL
        ),
        -- un run_id ne doit apparaître qu'une fois : on garde la ligne la plus récente en cas de doublon
        deduped AS (
            SELECT *, row_number() OVER (PARTITION BY run_id ORDER BY timestamp DESC) AS rn
            FROM valid
        )
        SELECT
            run_id,
            config_id,
            config_niveau_algo,
            config_nom_modele,
            config_param_count_modele,
            config_format_prompt,
            CAST(config_historique_active AS BOOLEAN) AS config_historique_active,
            CAST(config_priorisation_explicite AS BOOLEAN) AS config_priorisation_explicite,
            CAST(config_temperature AS DOUBLE) AS config_temperature,
            CAST(nb_pieces_ramassees AS INTEGER) AS nb_pieces_ramassees,
            CAST(nb_pieces_totales AS INTEGER) AS nb_pieces_totales,
            -- pénalité manquante = aucun contact enregistré, pas une valeur inconnue -> 0 explicite
            CAST(COALESCE(points_perdus_penalites, 0) AS INTEGER) AS points_perdus_penalites,
            CAST(duree_totale AS DOUBLE) AS duree_totale,
            CAST(timestamp AS TIMESTAMP) AS timestamp
        FROM deduped
        WHERE rn = 1
    """)

    clean_count = con.execute("SELECT count(*) FROM runs_clean").fetchone()[0]
    print(f"[runs]  bronze={raw_count} -> silver={clean_count} (exclus/dédupliqués: {raw_count - clean_count})")

    con.execute(f"COPY runs_clean TO '{SILVER_DIR / 'runs.parquet'}' (FORMAT PARQUET)")


def clean_steps(con: duckdb.DuckDBPyConnection) -> None:
    raw_count = con.execute(f"SELECT count(*) FROM read_parquet('{BRONZE_STEPS_GLOB}', union_by_name=True)").fetchone()[0]

    con.execute(f"""
        CREATE OR REPLACE TABLE steps_clean AS
        WITH raw AS (
            SELECT * FROM read_parquet('{BRONZE_STEPS_GLOB}', union_by_name=True)
        ),
        -- un pas sans run_id/step_index/timestamp n'est pas rattachable à un run : exclu explicitement
        valid AS (
            SELECT *
            FROM raw
            WHERE run_id IS NOT NULL
              AND step_index IS NOT NULL
              AND timestamp IS NOT NULL
        ),
        -- un (run_id, step_index) ne doit apparaître qu'une fois
        deduped AS (
            SELECT *, row_number() OVER (PARTITION BY run_id, step_index ORDER BY timestamp DESC) AS rn
            FROM valid
        )
        SELECT
            run_id,
            CAST(step_index AS INTEGER) AS step_index,
            CAST(position_row AS INTEGER) AS position_row,
            CAST(position_col AS INTEGER) AS position_col,
            action_choisie,
            -- une décision LLM non parsable => action invalide explicite, pas un NULL silencieux
            COALESCE(CAST(action_valid AS BOOLEAN), FALSE) AS action_valid,
            -- NULL légitime : plus aucune pièce sur la carte à ce pas (pas une valeur manquante à imputer)
            CAST(distance_cible_manhattan AS INTEGER) AS distance_cible_manhattan,
            CAST(target_row AS INTEGER) AS target_row,
            CAST(target_col AS INTEGER) AS target_col,
            COALESCE(CAST(contact_ennemi AS BOOLEAN), FALSE) AS contact_ennemi,
            CAST(COALESCE(points_lost_step, 0) AS INTEGER) AS points_lost_step,
            -- NULL légitime : LM Studio ne renvoie pas toujours l'usage token
            CAST(tokens_input AS INTEGER) AS tokens_input,
            CAST(tokens_output AS INTEGER) AS tokens_output,
            CAST(latence_ms AS DOUBLE) AS latence_ms,
            CAST(timestamp AS TIMESTAMP) AS timestamp
        FROM deduped
        WHERE rn = 1
    """)

    clean_count = con.execute("SELECT count(*) FROM steps_clean").fetchone()[0]
    print(f"[steps] bronze={raw_count} -> silver={clean_count} (exclus/dédupliqués: {raw_count - clean_count})")

    con.execute(f"COPY steps_clean TO '{SILVER_DIR / 'steps.parquet'}' (FORMAT PARQUET)")


def check_orphans(con: duckdb.DuckDBPyConnection) -> None:
    orphan_steps = con.execute("""
        SELECT count(DISTINCT s.run_id)
        FROM steps_clean s
        LEFT JOIN runs_clean r USING (run_id)
        WHERE r.run_id IS NULL
    """).fetchone()[0]
    runs_without_steps = con.execute("""
        SELECT count(*)
        FROM runs_clean r
        LEFT JOIN (SELECT DISTINCT run_id FROM steps_clean) s USING (run_id)
        WHERE s.run_id IS NULL
    """).fetchone()[0]

    if orphan_steps:
        print(f"⚠️  {orphan_steps} run_id présents dans steps mais absents de runs (fichier runs manquant/corrompu ?)")
    if runs_without_steps:
        print(f"⚠️  {runs_without_steps} run_id présents dans runs mais sans aucun pas dans steps")


def main() -> None:
    con = duckdb.connect()
    clean_runs(con)
    clean_steps(con)
    check_orphans(con)
    con.close()
    print(f"\nSilver écrit dans {SILVER_DIR}")


if __name__ == "__main__":
    main()
