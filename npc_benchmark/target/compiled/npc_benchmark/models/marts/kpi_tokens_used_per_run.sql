with run_tokens as (
    select run_id, sum(coalesce(tokens_input, 0) + coalesce(tokens_output, 0)) as tokens_run
    from "benchmark"."main"."stg_steps"
    group by run_id
)

select
    r.config_niveau_algo,
    r.config_nom_modele,
    r.config_format_prompt,
    avg(rt.tokens_run) as tokens_used_per_run
from "benchmark"."main"."stg_runs" r
join run_tokens rt using (run_id)
group by 1, 2, 3