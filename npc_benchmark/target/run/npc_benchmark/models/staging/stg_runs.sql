
  
  create view "benchmark"."main"."stg_runs__dbt_tmp" as (
    select *
from read_parquet('../../data/silver/runs.parquet')
  );
