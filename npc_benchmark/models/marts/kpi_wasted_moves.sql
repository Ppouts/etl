-- Un pas est "gaspillé" si le déplacement était invalide (mur/bord/ennemi bloquant),
-- ou s'il était valide mais n'a pas rapproché l'agent de sa cible (distance stable ou en hausse).
with ordered as (
    select
        run_id,
        step_index,
        action_valid,
        distance_cible_manhattan,
        lag(distance_cible_manhattan) over (partition by run_id order by step_index) as prev_distance
    from {{ ref('stg_steps') }}
),

flagged as (
    select
        run_id,
        case
            when not action_valid then 1
            when prev_distance is not null
                 and distance_cible_manhattan is not null
                 and distance_cible_manhattan >= prev_distance
                then 1
            else 0
        end as is_wasted
    from ordered
),

run_level as (
    select run_id, sum(is_wasted) as wasted_moves_run
    from flagged
    group by run_id
)

select
    r.config_niveau_algo,
    r.config_nom_modele,
    r.config_format_prompt,
    avg(rl.wasted_moves_run) as wasted_moves,
    count(*) as nb_runs
from {{ ref('stg_runs') }} r
join run_level rl using (run_id)
group by 1, 2, 3
