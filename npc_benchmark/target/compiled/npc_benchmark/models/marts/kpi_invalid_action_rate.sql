select
    r.config_niveau_algo,
    r.config_nom_modele,
    r.config_format_prompt,
    avg(case when not s.action_valid then 1.0 else 0.0 end) as invalid_action_rate
from "benchmark"."main"."stg_steps" s
join "benchmark"."main"."stg_runs" r using (run_id)
group by 1, 2, 3