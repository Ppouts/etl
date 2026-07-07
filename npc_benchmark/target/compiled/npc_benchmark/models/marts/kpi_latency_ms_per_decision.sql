select
    r.config_niveau_algo,
    r.config_nom_modele,
    r.config_format_prompt,
    avg(s.latence_ms) as latency_ms_per_decision
from "benchmark"."main"."stg_steps" s
join "benchmark"."main"."stg_runs" r using (run_id)
group by 1, 2, 3