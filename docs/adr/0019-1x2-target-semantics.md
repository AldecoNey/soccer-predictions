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

## Fuentes

Verificación directa contra los datos ya cargados en Neon (0 partidos con status ≠ finished/scheduled). Convención de mercado (cuotas 1-X-2 = tiempo reglamentario) basada en conocimiento general de la industria, no se citó una fuente específica por no ser una afirmación técnica verificable puntualmente.
