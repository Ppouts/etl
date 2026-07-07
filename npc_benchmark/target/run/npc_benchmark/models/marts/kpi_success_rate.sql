
  
    
    

    create  table
      "benchmark"."main"."kpi_success_rate__dbt_tmp"
  
    as (
      select
    config_niveau_algo,
    config_nom_modele,
    config_format_prompt,
    avg(case when nb_pieces_ramassees = nb_pieces_totales then 1.0 else 0.0 end) as success_rate,
    count(*) as nb_runs
from "benchmark"."main"."stg_runs"
group by 1, 2, 3
    );
  
  