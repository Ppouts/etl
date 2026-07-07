-- Score composite (0-100 en théorie, borné en pratique par success_rate) :
--   efficiency_score = (success_rate * 100) / (1 + tokens_used_per_run / 1000) / (1 + enemy_contacts)
--
-- Logique : success_rate porte tout le poids positif (une config qui ne finit jamais la carte
-- ne peut pas avoir un bon score, quel que soit son coût). Les deux facteurs de pénalité sont
-- des diviseurs "1 + x" plutôt que des soustractions : ça évite les scores négatifs, ça reste
-- doux (une config qui coûte 1000 tokens de plus par run perd ~moitié de son score plutôt que
-- d'être écrasée), et ça évite la division par zéro quand tokens_used_per_run ou enemy_contacts
-- valent 0. Le diviseur /1000 sur les tokens est un ordre de grandeur pour ce benchmark
-- (quelques appels LLM par run) ; à ajuster si les runs deviennent beaucoup plus longs.
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
from {{ ref('kpi_success_rate') }} sr
join {{ ref('kpi_tokens_used_per_run') }} tk
    using (config_niveau_algo, config_nom_modele, config_format_prompt)
join {{ ref('kpi_enemy_contacts') }} ec
    using (config_niveau_algo, config_nom_modele, config_format_prompt)
