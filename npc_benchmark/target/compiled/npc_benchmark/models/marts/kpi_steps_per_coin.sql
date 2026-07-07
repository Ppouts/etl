with run_steps as (
    select run_id, count(*) as nb_steps
    from "benchmark"."main"."stg_steps"
    group by run_id
),

run_level as (
    select
        r.config_niveau_algo,
        r.config_nom_modele,
        r.config_format_prompt,
        r.run_id,
        case when r.nb_pieces_ramassees > 0
            then rs.nb_steps::double / r.nb_pieces_ramassees
        end as steps_per_coin_run
    from "benchmark"."main"."stg_runs" r
    join run_steps rs using (run_id)
)

select
    config_niveau_algo,
    config_nom_modele,
    config_format_prompt,
    avg(steps_per_coin_run) as steps_per_coin,
    count(*) as nb_runs
from run_level
group by 1, 2, 3