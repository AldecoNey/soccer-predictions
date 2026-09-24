# ADR-0019 — Semántica oficial del target 1-X-2: 90 minutos + descuento

**Estado:** Aceptada
**Fecha:** 2026-09-20
**Decide:** CTO/Orquestador (Claude)

## Contexto

El sistema predice "1-X-2" (local/empate/visitante), pero nunca se había fijado por escrito, como decisión formal, a qué momento del partido corresponde ese resultado. Con solo Liga Profesional Argentina (formato liga, sin prórroga en fase regular) esto no generó ningún problema real — pero apenas se agregue una copa con fase eliminatoria (Copa Argentina, Libertadores — Sección 25 del brief), un partido puede terminar 1-1 en el marcador reglamentario y resolverse 5-4 por penales. Sin una definición explícita, sería ambiguo si el "1" de esa predicción se refiere al resultado de los 90 minutos o al desenlace final del partido (que decide quién avanza de fase).

## Decisión

**FulbolAI 1-X-2 = resultado al final del tiempo reglamentario (90 minutos + descuento/tiempo añadido), excluyendo explícitamente prórroga y definición por penales.**

Una victoria por penales después de un empate en los 90 minutos **no** es una victoria para el target 1-X-2 — sigue siendo un empate. Esto es consistente con cómo se leen las cuotas 1-X-2 de mercado en la industria (siempre "tiempo reglamentario" salvo que se indique explícitamente "incluyendo prórroga"), así que además evita ambigüedad al comparar contra el benchmark de bookmakers (ADR-0003).

### Estado actual de la ingesta (verificado, no asumido)

- `pipelines/ingest_historical_fixtures.py` trata `FT`, `AET` y `PEN` como `status="finished"` y usa `fx["goals"]["home"/"away"]` directamente como el resultado.
- Verificado contra los datos reales ya cargados: **cero partidos** con status distinto de `finished`/`scheduled` en toda la base — consistente con que Liga Profesional Argentina (fase regular, formato liga) no tiene partidos a prórroga/penales. No se verificó específicamente si `goals.home/away` de API-Football representa el marcador de 90' o el marcador final para un hipotético partido `AET`/`PEN` — no hace falta todavía porque no existe ningún caso real en los datos, pero **no se debe asumir sin verificar** cuando se agregue la primera competición con fase eliminatoria.

### Qué falta (deliberadamente, no ahora)

Los campos para representar esto correctamente en el esquema (`score_90`, `score_extra_time`, `penalties_home`, `penalties_away`, `qualified_team_id` o equivalentes) ya están identificados y deferidos en ADR-0013, con trigger explícito "al incorporar copas". Esta ADR no adelanta esa migración — solo fija la definición semántica por escrito, para que cuando se implemente, se implemente correctamente desde el primer intento (no haya que reinterpretar qué significaba "outcome" en los 2243+ resultados ya cargados).

### Guard defensivo agregado ahora

`pipelines/ingest_historical_fixtures.py` documenta explícitamente, en el punto donde se mapea `FINISHED_STATUSES`, que `AET`/`PEN` **no deben usarse como target 1-X-2 sin antes verificar** qué representa `goals.home/away` para esos casos — para que quien toque ese código al agregar la primera copa no lo pase por alto.

## Consecuencias

- Positivas: definición inequívoca antes de que exista el primer caso real ambiguo; evita tener que reinterpretar retroactivamente datos ya almacenados.
- Negativas: ninguna — es documentación, no cambia comportamiento actual.
- Trigger de revisión: al incorporar la primera competición con fase eliminatoria (Copa Argentina u otra) — ahí se implementan los campos deferidos en ADR-0013 y se verifica empíricamente qué representa `goals.home/away` en fixtures `AET`/`PEN` de API-Football, antes de ingerir el primer caso real.

## Actualización (2026-09-24): el trigger se disparó — el formato 2025+ de Liga Profesional Argentina SÍ tiene fase eliminatoria, y `goals` SÍ estaba mal para AET

Al validar `elo_tuned` con los folds 2025/2026 (evaluación separada, ver ADR-0024), se descubrió que **Liga Profesional Argentina cambió de formato en 2025** (30 equipos, fases Apertura/Clausura + playoffs) — algo que no existía cuando se escribió esta ADR y que **no** requirió agregar una copa nueva, como se asumía acá. Verificado contra los 45 partidos de fase eliminatoria ya jugados en 2025/2026: **12 fueron a AET/PEN** (4 AET, 8 PEN).

Se verificó contra la API real (no asumido) que la advertencia de esta ADR era fundada: en los **4 casos AET, `goals.home/away` SÍ incluía el gol de alargue** — ej. fixture 1486749 (Deportivo Riestra vs Barracas Central): `score.fulltime`=0-0, pero `goals`=0-1 (el gol de alargue quedó mezclado). Los 8 casos PEN no tuvieron este problema, pero por casualidad: esa ronda del certamen va directo de 90' a penales sin alargue, así que ahí `goals` y `fulltime` coincidían — no porque `goals` fuera la fuente correcta en general.

**Consecuencia real, no solo teórica:** 4 resultados en `results` estaban mal guardados — los 4 casos AET, donde `outcome` decía "gana alguien" cuando en realidad los 90' habían sido empate:

| Fixture | Partido | Guardado (mal) | Corregido (90') |
|---|---|---|---|
| 1486749 | Riestra vs Barracas Central | 0-1 (away) | 0-0 (draw) |
| 1544177 | Boca Juniors vs Huracán | 2-3 (away) | 1-1 (draw) |
| 1544850 | Argentinos JRS vs Huracán | 1-0 (home) | 0-0 (draw) |
| 1544851 | Rosario Central vs Racing | 2-1 (home) | 1-1 (draw) |

**Fix aplicado:** `pipelines/ingest_historical_fixtures.py::resolve_90min_score()` ahora usa `score.fulltime.home/away` como fuente de verdad (con fallback a `goals` solo si `fulltime` faltara), reemplazando el uso directo de `goals`. A diferencia de `predictions` (ADR-0008, append-only), `Result` ahora SÍ se corrige en re-ingesta si `score.fulltime` difiere de lo guardado — no es "reescribir historia", es arreglar un dato mal extraído hacia la verdad ya conocida de la API. 5 tests nuevos (`test_ingest_historical_fixtures.py`) sobre la función pura, incluyendo los 2 casos reales exactos (AET con gol de alargue, PEN sin alargue) para que esto no se repita en silencio.

**Impacto en experimentos ya cerrados (ADR-0011, ADR-0022):** 4 partidos sobre ~1662 evaluados (0.24%) — se revisó el efecto en la evaluación de `elo_tuned` (la más reciente y la única con veredicto ajustado, ver ADR-0024) y el cambio fue marginal (variación de centésimas en log_loss, muy por debajo del ruido estadístico ya identificado). No se re-corrieron ADR-0011/ADR-0022 — ambos resultados eran negativos y consistentes across folds; un cambio de este tamaño no tiene margen realista para revertir esas conclusiones.

## Fuentes

Verificación directa contra los datos ya cargados en Neon (0 partidos con status ≠ finished/scheduled, al momento original de esta ADR). Convención de mercado (cuotas 1-X-2 = tiempo reglamentario) basada en conocimiento general de la industria, no se citó una fuente específica por no ser una afirmación técnica verificable puntualmente. Actualización 2026-09-24: verificación directa contra `GET /fixtures?id=<fixture>` de API-Football para los 45 partidos de fase eliminatoria de 2025/2026 y sus objetos `score.fulltime`/`score.extratime`/`score.penalty` completos.
