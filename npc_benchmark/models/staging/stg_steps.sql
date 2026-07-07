select *
from read_parquet('{{ var("silver_path") }}/steps.parquet')
