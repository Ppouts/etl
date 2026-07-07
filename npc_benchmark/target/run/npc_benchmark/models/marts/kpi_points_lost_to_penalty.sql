
  
    
    

    create  table
      "benchmark"."main"."kpi_points_lost_to_penalty__dbt_tmp"
  
    as (
      select
    config_niveau_algo,
    config_nom_modele,
    config_format_prompt,
    avg(points_perdus_penalites) as points_lost_to_penalty,
    count(*) as nb_runs
from "benchmark"."main"."stg_runs"
group by 1, 2, 3
    );
  
  