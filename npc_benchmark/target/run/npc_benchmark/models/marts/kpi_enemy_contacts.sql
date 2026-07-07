
  
    
    

    create  table
      "benchmark"."main"."kpi_enemy_contacts__dbt_tmp"
  
    as (
      with run_contacts as (
    select run_id, sum(case when contact_ennemi then 1 else 0 end) as contacts_run
    from "benchmark"."main"."stg_steps"
    group by run_id
)

select
    r.config_niveau_algo,
    r.config_nom_modele,
    r.config_format_prompt,
    avg(rc.contacts_run) as enemy_contacts
from "benchmark"."main"."stg_runs" r
join run_contacts rc using (run_id)
group by 1, 2, 3
    );
  
  