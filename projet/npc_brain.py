# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.4
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %%
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel

import os
import re
import json
import time
import uuid
import hashlib
from enum import Enum
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

# %%
load_dotenv()

# %%
LLM_API_URL = os.environ["LLM_API_URL"]
LLM_API_TOKEN = os.environ["LLM_API_TOKEN"]
MODEL = "google/gemma-4-e2b"

# %%
client = OpenAI(
    base_url=LLM_API_URL,
    api_key=LLM_API_TOKEN
)

# %%
BRONZE_STEPS_DIR = Path("../data/bronze/steps")
BRONZE_RUNS_DIR = Path("../data/bronze/runs")
BRONZE_STEPS_DIR.mkdir(parents=True, exist_ok=True)
BRONZE_RUNS_DIR.mkdir(parents=True, exist_ok=True)

GOLD_POINTS = 1
ENEMY_PENALTY = 5

MODEL_PARAM_COUNTS = {
    "google/gemma-4-e2b": "2B",
    "google/gemma-4-12b-qat": "12B",
}

# %% [markdown]
# # Modélisation du monde

# %%
VOID        = 0
PLAYER      = 1
ENNEMY      = 2
GOLD        = 3

SYMBOLS = {VOID: "·", PLAYER: "👤", ENNEMY: "👹", GOLD: "💰"}

# %%
initial_map = np.array([
    [0, 3, 0, 0, 0, 0, 0],
    [0, 1, 0, 0, 2, 0, 3],
    [0, 3, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 3],
    [0, 0, 0, 0, 0, 0, 0],
])
initial_map


# %% [markdown]
# # Couche de contrat

# %%
class Direction(str, Enum):
    HAUT       = "HAUT"
    BAS        = "BAS"
    GAUCHE     = "GAUCHE"
    DROITE     = "DROITE"


class PlayerDecision(BaseModel):
    direction: Direction


MOVES = {
    "HAUT":     (-1, 0),
    "BAS":      ( 1,  0),
    "GAUCHE":   ( 0,  -1),
    "DROITE":   ( 0,   1),
}


# %%
class RunConfig(BaseModel):
    niveau_algo: str = "llm_only"
    nom_modele: str
    param_count_modele: str = "unknown"
    format_prompt: str = "fr_v1"
    historique_active: bool = True
    priorisation_explicite: bool = True
    temperature: float = 0.0

    def config_id(self) -> str:
        payload = json.dumps(self.model_dump(), sort_keys=True)
        return hashlib.sha1(payload.encode()).hexdigest()[:8]


# %% [markdown]
# # Moteur de perception

# %%
def localize(world_map, entity):
    positions = np.argwhere(world_map == entity)
    return positions


# %%
def compute_distances(entities_positions, reference_pos):
    if (len(entities_positions) == 0):
        return np.array([])

    v = entities_positions - reference_pos
    distances = np.abs(v).sum(axis=1)

    return distances.astype(int)


# %%
def perception(world_map):

    player_position = localize(world_map, PLAYER)
    golds_positions = localize(world_map, GOLD)
    ennemies_positions = localize(world_map, ENNEMY)

    golds_distances = compute_distances(golds_positions, player_position)
    ennemies_distances = compute_distances(ennemies_positions, player_position)

    if len(golds_positions) > 0:
        nearest_idx = int(np.argmin(golds_distances))
        nearest_gold = golds_positions[nearest_idx]
        nearest_gold_delta = {
            "row": int(nearest_gold[0] - player_position[0][0]),
            "col": int(nearest_gold[1] - player_position[0][1]),
        }
        nearest_gold_pos = {"row": int(nearest_gold[0]), "col": int(nearest_gold[1])}
        nearest_gold_distance = int(golds_distances[nearest_idx])
    else:
        nearest_gold_delta = {"row": 0, "col": 0}
        nearest_gold_pos = None
        nearest_gold_distance = None

    all_ennemies_deltas = [
        {
            "row": int(e[0] - player_position[0][0]),
            "col": int(e[1] - player_position[0][1]),
        }
        for e in ennemies_positions
    ]

    return {
        "ennemies_distances": ennemies_distances.tolist(),
        "ennemies_count": len(ennemies_distances),
        "all_ennemies_deltas": all_ennemies_deltas,
        "golds_distances": golds_distances.tolist(),
        "golds_count": len(golds_distances),
        "nearest_gold_delta": nearest_gold_delta,
        "nearest_gold_pos": nearest_gold_pos,
        "nearest_gold_distance": nearest_gold_distance,
    }


# %%
def show_map(world_map):
    for row in world_map:
        print("\t".join(SYMBOLS.get(cell, "?") for cell in row))
    print('-----------------------------------------------------')


# %% [markdown]
# # Moteur de déplacement

# %%
def allowed_move(world_map: np.ndarray, pos):
    n_rows, n_cols = world_map.shape
    r, c = pos

    if r < 0 or c < 0 or r >= n_rows or c >= n_cols:
        return False

    return world_map[r, c] in (VOID, GOLD)


# %%
def move(world_map: np.ndarray, old_pos, new_pos):
    if not allowed_move(world_map, new_pos):
        return old_pos
    
    entity = world_map[old_pos[0], old_pos[1]]
    world_map[old_pos[0], old_pos[1]] = VOID
    world_map[new_pos[0], new_pos[1]] = entity

    return new_pos


# %% [markdown]
# # Moteur de décision

# %%
def decide(player_perception, config: RunConfig) -> tuple[PlayerDecision | None, dict]:
    delta = player_perception["nearest_gold_delta"]
    history = player_perception.get("move_history", [])

    gold_collected = player_perception.get("gold_collected", 0)
    total_gold = player_perception.get("total_gold", "?")
    is_oscillating = player_perception.get("is_oscillating", False) and config.historique_active
    oscillation_warning = "\n    ⚠️ ATTENTION : Tu alternes les mêmes mouvements en boucle ! Choisis une direction DIFFÉRENTE : GAUCHE ou DROITE." if is_oscillating else ""

    ennemies_deltas = player_perception.get("all_ennemies_deltas", [])
    if ennemies_deltas:
        ennemy_lines = []
        for i, (ed, dist) in enumerate(zip(ennemies_deltas, player_perception["ennemies_distances"])):
            ennemy_lines.append(
                f"  - Ennemi {i+1}: {abs(ed['row'])} ligne(s) vers le {'BAS' if ed['row'] > 0 else 'HAUT'}, "
                f"{abs(ed['col'])} colonne(s) vers la {'DROITE' if ed['col'] > 0 else 'GAUCHE'} (distance: {dist})"
            )
        ennemy_info = "\n".join(ennemy_lines)
    else:
        ennemy_info = "  - aucun ennemi"

    history_line = f"    - Historique des derniers mouvements : {history[-5:] if history else 'aucun'}\n" if config.historique_active else ""
    priority_line = "    - Priorité : éviter l'ennemi > ramasser l'or\n" if config.priorisation_explicite else ""

    prompt = f"""
    # Contexte
    Tu es un joueur sur une grille. Ramasse tout l'or pour gagner. Evite l'ennemi : le contact te fait perdre des points mais la partie continue.

    # Ton état
    - Or collecté : {gold_collected}/{total_gold}
    - Or restant sur la carte : {player_perception["golds_count"]}

    # Perception
    - Or le plus proche : {delta["row"]} lignes vers le {"BAS" if delta["row"] > 0 else "HAUT"}, {abs(delta["col"])} colonnes vers la {"DROITE" if delta["col"] > 0 else "GAUCHE"}
    - Ennemis (EVITE-LES, le contact fait perdre {ENEMY_PENALTY} points) :
{ennemy_info}
{history_line}
    # Règles
    - Tu ne peux te déplacer que d'une case à la fois : HAUT, BAS, GAUCHE, DROITE
    - ATTENTION : marcher sur l'ennemi fait perdre {ENEMY_PENALTY} points (le déplacement est bloqué, comme un mur). Ne va JAMAIS dans la direction de l'ennemi si sa distance est <= 1
{priority_line}    - Si tu répètes les mêmes mouvements, essaie GAUCHE ou DROITE pour contourner{oscillation_warning}

    # Réponse
    Réponds UNIQUEMENT avec un JSON: {{"direction": "HAUT"}}  (HAUT, BAS, GAUCHE ou DROITE)
    """

    started_at = time.perf_counter()
    response = client.chat.completions.create(
        model=config.nom_modele,
        messages=[{"role": "user", "content": prompt}],
        temperature=config.temperature,
    )
    latency_ms = (time.perf_counter() - started_at) * 1000

    usage = getattr(response, "usage", None)
    meta = {
        "tokens_input": getattr(usage, "prompt_tokens", None) if usage else None,
        "tokens_output": getattr(usage, "completion_tokens", None) if usage else None,
        "latency_ms": round(latency_ms, 1),
    }

    raw = response.choices[0].message.content or ""
    match = re.search(r'\{[^}]+\}', raw)
    if not match:
        print("Pas de JSON trouve")
        return None, meta
    try:
        return PlayerDecision.model_validate(json.loads(match.group())), meta
    except Exception as e:
        print("Parse error:", e)
        return None, meta


# %% [markdown]
# # Game loop (simulation)

# %%
def game_loop(world_map: np.ndarray, config: RunConfig, max_turns: int = 10) -> dict:
    world_map = world_map.copy()
    move_history = []
    gold_collected = 0
    total_gold = int(np.sum(world_map == GOLD))

    run_id = str(uuid.uuid4())
    config_id = config.config_id()
    run_started_at = datetime.now(timezone.utc)
    run_started_perf = time.perf_counter()

    points = 0
    points_perdus_penalites = 0
    steps_log = []

    for turn in range(max_turns):
        print(f"\n =================== [Turn {turn + 1}] ===================")
        show_map(world_map)

        player_pos = localize(world_map, PLAYER)[0]
        old_pos = (int(player_pos[0]), int(player_pos[1]))

        is_oscillating = (
            len(move_history) >= 4 and
            move_history[-1] == move_history[-3] and
            move_history[-2] == move_history[-4] and
            move_history[-1] != move_history[-2]
        )

        p = perception(world_map)
        p["move_history"] = move_history
        p["gold_collected"] = gold_collected
        p["total_gold"] = total_gold
        p["is_oscillating"] = is_oscillating
        p["all_gold_collected"] = (gold_collected == total_gold)

        distance_cible_manhattan = p["nearest_gold_distance"]
        target_pos = p["nearest_gold_pos"]

        decision, decision_meta = decide(p, config)

        contact_ennemi = False
        action_valid = False
        points_lost_step = 0
        action_choisie = None

        if decision is not None:
            action_choisie = decision.direction.value
            print(f"\t → LLM decision: {action_choisie}")
            move_history.append(action_choisie)

            d_row, d_col = MOVES[action_choisie]
            new_pos = (old_pos[0] + d_row, old_pos[1] + d_col)
            nr, nc = new_pos

            if 0 <= nr < world_map.shape[0] and 0 <= nc < world_map.shape[1]:
                cell = world_map[nr, nc]

                if cell == ENNEMY:
                    contact_ennemi = True
                    points_lost_step = ENEMY_PENALTY
                    points -= ENEMY_PENALTY
                    points_perdus_penalites += ENEMY_PENALTY
                    print(f"\t 💥 Contact ennemi ! -{ENEMY_PENALTY} points (score: {points})")

                if cell == GOLD:
                    gold_collected += 1
                    points += GOLD_POINTS
                    print(f"\t 💰 Or ramassé ! ({gold_collected}/{total_gold})")

            moved_to = move(world_map, old_pos, new_pos)
            action_valid = (moved_to != old_pos)

        steps_log.append({
            "run_id": run_id,
            "step_index": turn,
            "position_row": old_pos[0],
            "position_col": old_pos[1],
            "action_choisie": action_choisie,
            "action_valid": action_valid,
            "distance_cible_manhattan": distance_cible_manhattan,
            "target_row": target_pos["row"] if target_pos else None,
            "target_col": target_pos["col"] if target_pos else None,
            "contact_ennemi": contact_ennemi,
            "points_lost_step": points_lost_step,
            "tokens_input": decision_meta["tokens_input"],
            "tokens_output": decision_meta["tokens_output"],
            "latence_ms": decision_meta["latency_ms"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if gold_collected == total_gold:
            print(f"\n🏆 VICTOIRE ! Tout l'or ramassé en {turn + 1} tours !")
            show_map(world_map)
            break
    else:
        print(f"\n⏱️ Temps écoulé ! Or collecté: {gold_collected}/{total_gold}")

    duree_totale = time.perf_counter() - run_started_perf

    steps_df = pd.DataFrame(steps_log)
    run_row = {
        "run_id": run_id,
        "config_id": config_id,
        "config_niveau_algo": config.niveau_algo,
        "config_nom_modele": config.nom_modele,
        "config_param_count_modele": config.param_count_modele,
        "config_format_prompt": config.format_prompt,
        "config_historique_active": config.historique_active,
        "config_priorisation_explicite": config.priorisation_explicite,
        "config_temperature": config.temperature,
        "nb_pieces_ramassees": gold_collected,
        "nb_pieces_totales": total_gold,
        "points_perdus_penalites": points_perdus_penalites,
        "duree_totale": round(duree_totale, 3),
        "timestamp": run_started_at.isoformat(),
    }
    runs_df = pd.DataFrame([run_row])

    file_stamp = run_started_at.strftime("%Y%m%dT%H%M%S")
    steps_path = BRONZE_STEPS_DIR / f"run_{file_stamp}_{config_id}.parquet"
    runs_path = BRONZE_RUNS_DIR / f"run_{file_stamp}_{config_id}.parquet"
    steps_df.to_parquet(steps_path, index=False)
    runs_df.to_parquet(runs_path, index=False)

    print(f"\n📦 Bronze écrit : {steps_path.name} ({len(steps_df)} pas) / {runs_path.name}")

    return run_row


# %%
default_config = RunConfig(
    nom_modele=MODEL,
    param_count_modele=MODEL_PARAM_COUNTS.get(MODEL, "unknown"),
)

game_loop(world_map=initial_map, max_turns=10, config=default_config)

# %% [markdown]
# # ToDo
#
# - Ajouter de vraies variantes pour niveau_algo (ex: couche algorithmique en plus du LLM) et format_prompt (aujourd'hui un seul de chaque, juste loggés)
# - Historiser plusieurs cartes (`initial_map`) pour varier la difficulté entre runs
