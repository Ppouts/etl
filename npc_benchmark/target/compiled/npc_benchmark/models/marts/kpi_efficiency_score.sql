select
    sr.config_niveau_algo,
    sr.config_nom_modele,
    sr.config_format_prompt,
    sr.success_rate,
    tk.tokens_used_per_run,
    ec.enemy_contacts,
    round(
        (sr.success_rate * 100)
        / (1 + tk.tokens_used_per_run / 1000.0)
        / (1 + ec.enemy_contacts),
        2
    ) as efficiency_score
from "benchmark"."main"."kpi_success_rate" sr
join "benchmark"."main"."kpi_tokens_used_per_run" tk
    using (config_niveau_algo, config_nom_modele, config_format_prompt)
join "benchmark"."main"."kpi_enemy_contacts" ec
    using (config_niveau_algo, config_nom_modele, config_format_prompt)