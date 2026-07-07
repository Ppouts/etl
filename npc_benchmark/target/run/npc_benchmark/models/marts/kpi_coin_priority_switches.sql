
  
    
    

    create  table
      "benchmark"."main"."kpi_coin_priority_switches__dbt_tmp"
  
    as (
      with ordered as (
    select
        run_id,
        step_index,
        position_row,
        position_col,
        target_row,
        target_col,
        lag(target_row) over (partition by run_id order by step_index) as prev_target_row,
        lag(target_col) over (partition by run_id order by step_index) as prev_target_col
    from "benchmark"."main"."stg_steps"
),

flagged as (
    select
        run_id,
        case
            when prev_target_row is not null
                 and (target_row is distinct from prev_target_row
                      or target_col is distinct from prev_target_col)
                 and not (position_row = prev_target_row and position_col = prev_target_col)
                then 1
            else 0
        end as is_switch
    from ordered
),

run_level as (
    select run_id, sum(is_switch) as switches_run
    from flagged
    group by run_id
)

select
    r.config_niveau_algo,
    r.config_nom_modele,
    r.config_format_prompt,
    avg(rl.switches_run) as coin_priority_switches
from "benchmark"."main"."stg_runs" r
join run_level rl using (run_id)
group by 1, 2, 3
    );
  
  