
  
    
    

    create  table
      "benchmark"."main"."kpi_rolling_avg_distance__dbt_tmp"
  
    as (
      with rolling as (
    select
        r.config_niveau_algo,
        r.config_nom_modele,
        r.config_format_prompt,
        avg(s.distance_cible_manhattan) over (
            partition by s.run_id order by s.step_index
            rows between 2 preceding and current row
        ) as rolling_distance
    from "benchmark"."main"."stg_steps" s
    join "benchmark"."main"."stg_runs" r using (run_id)
    where s.distance_cible_manhattan is not null
)

select
    config_niveau_algo,
    config_nom_modele,
    config_format_prompt,
    avg(rolling_distance) as rolling_avg_distance
from rolling
group by 1, 2, 3
    );
  
  