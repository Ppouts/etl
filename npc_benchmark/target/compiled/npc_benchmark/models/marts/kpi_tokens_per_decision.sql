select
    r.config_niveau_algo,
    r.config_nom_modele,
    r.config_format_prompt,
    avg(coalesce(s.tokens_input, 0) + coalesce(s.tokens_output, 0)) as tokens_per_decision
from "benchmark"."main"."stg_steps" s
join "benchmark"."main"."stg_runs" r using (run_id)
group by 1, 2, 3