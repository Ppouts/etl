# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.4
#   kernelspec:
#     display_name: .venv (3.13.3)
#     language: python
#     name: python3
# ---

# %%
import numpy as np
from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel

import os
from enum import Enum

# %%
load_dotenv()

# %%
LLM_API_URL = os.environ["LLM_API_URL"]
LLM_API_TOKEN = os.environ["LLM_API_TOKEN"]
MODEL = "google/gemma-4-e2b"

# %%
# LLM_API_URL = os.environ["LMSTUDIO_BASE_URL"]
# LLM_API_TOKEN = os.environ["LM_API_TOKEN"]
# MODEL = "gemma-4-26B"

# %%
client = OpenAI(
    base_url=LLM_API_URL,
    api_key=LLM_API_TOKEN
)

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
    [0, 1, 0, 0, 2, 0, 3], # (1, 1) # (1, 4) # (1, 6)
    [0, 3, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 0],
    [0, 0, 0, 0, 0, 0, 3], # (5, 6)
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
    distances = np.linalg.norm(v, axis=1)
 
    return np.round(distances, 2)


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
    else:
        nearest_gold_delta = {"row": 0, "col": 0}

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
    
    return world_map[r, c] in (VOID, GOLD, ENNEMY)


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
def decide(player_perception) -> PlayerDecision | None:
    delta = player_perception["nearest_gold_delta"]
    history = player_perception.get("move_history", [])

    gold_collected = player_perception.get("gold_collected", 0)
    total_gold = player_perception.get("total_gold", "?")
    is_oscillating = player_perception.get("is_oscillating", False)
    oscillation_warning = "\n    ⚠️ ATTENTION : Tu alternes les mêmes mouvements en boucle ! Choisis une direction DIFFÉRENTE : GAUCHE ou DROITE." if is_oscillating else ""
    all_gold = player_perception.get("all_gold_collected", False)

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

    prompt = f"""
    # Contexte
    Tu es un joueur sur une grille. Ramasse tout l'or pour gagner. Evite l'ennemi ou c'est Game Over.

    # Ton état
    - Or collecté : {gold_collected}/{total_gold}
    - Or restant sur la carte : {player_perception["golds_count"]}

    # Perception
    - Or le plus proche : {delta["row"]} lignes vers le {"BAS" if delta["row"] > 0 else "HAUT"}, {abs(delta["col"])} colonnes vers la {"DROITE" if delta["col"] > 0 else "GAUCHE"}
    - Ennemis (EVITE-LES, marcher dessus = Game Over) :
{ennemy_info}
    - Historique des derniers mouvements : {history[-5:] if history else "aucun"}

    # Règles
    - Tu ne peux te déplacer que d'une case à la fois : HAUT, BAS, GAUCHE, DROITE
    - DANGER ABSOLU : marcher sur l'ennemi = Game Over. Ne va JAMAIS dans la direction de l'ennemi si sa distance est <= 1
    - Priorité : éviter l'ennemi > ramasser l'or
    - Si tu répètes les mêmes mouvements, essaie GAUCHE ou DROITE pour contourner{oscillation_warning}

    # Réponse
    Réponds UNIQUEMENT avec un JSON: {{"direction": "HAUT"}}  (HAUT, BAS, GAUCHE ou DROITE)
    """

    print(str(player_perception))

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    import json
    raw = response.choices[0].message.content
    try:
        return PlayerDecision.model_validate(json.loads(raw))
    except Exception:
        return None


# %% [markdown]
# # Game loop (simulation)

# %%
def game_loop(world_map: np.ndarray, max_turns = 10):
    world_map = world_map.copy()
    move_history = []
    gold_collected = 0
    total_gold = int(np.sum(world_map == GOLD))

    for turn in range(max_turns):
        print(f"\n =================== [Turn {turn + 1}] ===================")
        show_map(world_map)

        player_pos = localize(world_map, PLAYER)[0]

        # Détection d'oscillation (ex: HAUT BAS HAUT BAS)
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

        decision: PlayerDecision | None = decide(p)

        if decision is not None:
            print(f"\t → LLM decision: {decision.direction.value}")
            move_history.append(decision.direction.value)

            d_row, d_col = MOVES[decision.direction.value]
            new_pos = (player_pos[0] + d_row, player_pos[1] + d_col)
            nr, nc = new_pos

            if 0 <= nr < world_map.shape[0] and 0 <= nc < world_map.shape[1]:
                cell = world_map[nr, nc]

                if cell == ENNEMY:
                    print(f"\n💀 GAME OVER ! Ennemi touché au tour {turn + 1}. Or collecté: {gold_collected}/{total_gold}")
                    show_map(world_map)
                    return

                if cell == GOLD:
                    gold_collected += 1
                    print(f"\t 💰 Or ramassé ! ({gold_collected}/{total_gold})")
                    if gold_collected == total_gold:
                        print(f"\n🏆 VICTOIRE ! Tout l'or ramassé en {turn + 1} tours !")
                        show_map(world_map)
                        return

            new_pos = move(world_map, player_pos, new_pos)

    print(f"\n⏱️ Temps écoulé ! Or collecté: {gold_collected}/{total_gold}")


# %%
game_loop(world_map=initial_map, max_turns=10)

# %% [markdown]
# # ToDo
#
# - Mettre en place le ramassage d'or → Fin de partie
# - Mettre en place la perception directionnelle
