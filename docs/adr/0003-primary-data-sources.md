# ADR-0003 — Fuentes de datos primarias para Primera División Argentina

**Estado:** Aceptada, con puntos abiertos marcados para validación temprana
**Fecha:** 2026-09-19
**Decide:** CTO/Orquestador (Claude), con aprobación del usuario sobre gasto (Sección "Decisiones para el usuario" del documento maestro)

## Contexto

Necesitamos fixtures, resultados, alineaciones, lesiones y estadísticas de partido para la Liga Profesional de Fútbol Argentina, dentro de un presupuesto total de USD 30/mes (compartido con hosting, ver ADR-0002, que ya deja ~$26-30/mes libres para datos). Investigación de proveedores realizada el 2026-09-19.

## Opciones consideradas

| Proveedor | Veredicto |
|---|---|
| API-Football (api-sports.io) | Cobertura confirmada de Liga Profesional (league ID 44): fixtures, alineaciones, lesiones, stats, odds. Free: 100 req/día. Pro: $19/mes, 7500 req/día |
| football-data.org | Free tier NO incluye Argentina (solo top-5 europeas) → descartado para MVP |
| Sportmonks | Plan free cubre solo 2 ligas, no confirmado si incluye Argentina; Starter $29/mes agota casi todo el presupuesto → descartado por ahora |
| TheSportsDB | Datos poco profundos (metadata, no stats de rendimiento) → solo como fallback de metadata/escudos |
| SofaScore | Excelente cobertura pero sin API oficial; ToS no permite scraping estructurado → descartado como dependencia |
| StatsBomb Open Data / Understat | No cubren la liga argentina regular → descartados |
| FBref / Sports-Reference | Scraping automatizado explícitamente prohibido por ToS (incluye cláusula específica contra su uso para entrenar modelos) → solo uso manual puntual, nunca automatizado |
| Promiedos (no oficial) | Buena cobertura pero sin API pública/ToS, sin histórico → solo como fuente de verificación manual, no como dependencia de pipeline |
| rhinoah/futbol-argentino-data (GitHub) | Dataset abierto, ~22.270 partidos desde 2016, gratis → útil para bootstrap histórico |
| The Odds API (para benchmark de cuotas) | Free: 500 créditos/mes; cobertura de Liga Profesional Argentina **no confirmada** — pendiente de verificar con cuenta de prueba |

## Decisión

1. **Fuente primaria en vivo:** API-Football, plan **free** (100 req/día, 10 req/min) para el arranque del MVP. Cubre fixtures, resultados, alineaciones, lesiones y stats de partido de la Liga Profesional Argentina.
2. **Bootstrap histórico:** dataset `rhinoah/futbol-argentino-data` (GitHub, gratis) para poblar historial 2016+ antes de depender exclusivamente de las llamadas diarias a la API, validando que ambas fuentes coincidan en resultados conocidos (control de calidad cruzado).
3. **Metadata complementaria (escudos, nombres alternativos):** TheSportsDB, free tier, uso opcional y no crítico.
4. **Benchmark de cuotas (NO feature del modelo, solo comparación externa):** The Odds API, free tier, **condicionado** a confirmar en la Fase 0 que su catálogo de "sports" incluye la Liga Profesional Argentina. Si no la incluye, se documenta como benchmark no disponible en V1 y se reevalúa.
5. **Reserva de presupuesto:** si el free tier de API-Football (100 req/día) resulta insuficiente en volumen (por ejemplo, al escalar a más ligas o necesitar más profundidad histórica), se activa el plan Pro ($19/mes), dejando aun así margen dentro de los $30/mes totales. Este upgrade requiere confirmación del usuario porque implica gasto real (ver Sección P del documento maestro).
6. **Explícitamente prohibido:** scraping automatizado de FBref, SofaScore o Promiedos como parte de pipelines productivos, por riesgo de ToS y de discontinuidad. Se permiten solo consultas manuales puntuales para auditoría cruzada de casos dudosos.

## Consecuencias

- Positivas: arranque a costo $0, con ruta de upgrade clara y acotada si el volumen lo exige.
- Negativas / deuda técnica aceptada: 100 req/día es un límite ajustado si se necesitan alineaciones/lesiones actualizadas con frecuencia cerca del kickoff (T-2h); el diseño del pipeline (Fase 2) debe presupuestar cuidadosamente las llamadas diarias por partido y por snapshot.
- Riesgo abierto: no se confirmó si The Odds API cubre la Liga Profesional Argentina — la Fase 0 debe verificarlo con una cuenta de prueba antes de construir el módulo de benchmark de bookmakers.
- Trigger de revisión: si API-Football discontinúa el free tier, cambia su cobertura de Argentina, o si el volumen de requests necesario supera el free tier de forma sostenida.

## Fuentes

- https://www.api-football.com/pricing (consultado 2026-09-19)
- https://www.football-data.org/pricing (consultado 2026-09-19)
- https://www.sportmonks.com/football-api/plans-pricing/ (consultado 2026-09-19)
- https://www.thesportsdb.com/pricing (consultado 2026-09-19)
- https://sofascore.helpscoutdocs.com/article/129-sports-data-api-availability (consultado 2026-09-19)
- https://www.sports-reference.com/bot-traffic.html y /data_use.html (consultado 2026-09-19)
- https://github.com/statsbomb/open-data (consultado 2026-09-19)
- https://the-odds-api.com/ (consultado 2026-09-19)
- https://github.com/rhinoah/futbol-argentino-data (consultado 2026-09-19; verificar licencia del repo antes de uso comercial)
