
  
  create view "benchmark"."main"."stg_steps__dbt_tmp" as (
    select *
from read_parquet('../../data/silver/steps.parquet')
  );
