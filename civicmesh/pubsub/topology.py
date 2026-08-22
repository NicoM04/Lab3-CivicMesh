"""Topología geográfica y adyacencia de comunas."""

# Grafo de adyacencia comunal 
COMUNA_ADYACENCIA: dict[str, list[str]] = {
    "santiago": ["providencia", "estacion_central", "recoleta", "independencia", "san_miguel", "san_joaquin", "quinta_normal"],
    "providencia": ["santiago", "nunoa", "las_condes", "vitacura", "recoleta"],
    "nunoa": ["providencia", "santiago", "macul", "san_joaquin", "penalolen", "la_reina"],
    "las_condes": ["providencia", "vitacura", "la_reina", "lo_barnechea"],
    "recoleta": ["santiago", "providencia", "independencia", "huechuraba", "conchali"],
    "estacion_central": ["santiago", "quinta_normal", "cerrillos", "pedro_aguirre_cerda", "lo_prado"],
    "san_miguel": ["santiago", "san_joaquin", "pedro_aguirre_cerda", "san_ramon", "la_cisterna"],
    "macul": ["nunoa", "san_joaquin", "penalolen", "la_florida"],
    "independencia": ["santiago", "recoleta", "conchali", "renca"],
    "quinta_normal": ["santiago", "estacion_central", "renca", "cerro_navia", "lo_prado"],
    "san_joaquin": ["santiago", "nunoa", "macul", "san_miguel", "la_florida"],
    "vitacura": ["las_condes", "providencia", "huechuraba", "lo_barnechea"],
    "la_reina": ["nunoa", "las_condes", "penalolen"],
    "penalolen": ["nunoa", "macul", "la_reina", "la_florida"]
}
