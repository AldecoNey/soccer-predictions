# ADR-0003 — Fuentes de datos primarias para Primera División Argentina

**Estado:** Aceptada, con puntos abiertos marcados para validación temprana
**Fecha:** 2026-09-19
**Decide:** CTO/Orquestador (Claude), con aprobación del usuario sobre gasto (Sección "Decisiones para el usuario" del documento maestro)

## Contexto

Necesitamos fixtures, resultados, alineaciones, lesiones y estadísticas de partido para la Liga Profesional de Fútbol Argentina, dentro de un presupuesto total de USD 30/mes (compartido con hosting, ver ADR-0002, que ya deja ~$26-30/mes libres para datos). Investigación de proveedores realizada el 2026-09-19.

## Opciones consideradas

| Proveedor | Veredicto |
|---|---|
| API-Football (api-sports.io) | Cobertura confirmada de Liga Profesional (**league ID 128** — ver nota de corrección abajo): fixtures, alineaciones, lesiones, stats, odds. Free: 100 req/día. Pro: $19/mes, 7500 req/día |
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

## Corrección post-verificación (2026-09-19, Fase 2)

La investigación inicial (fork de research) reportó **league ID 44** para Liga Profesional Argentina en API-Football. Al verificar contra la API real con una cuenta activa, se confirmó que **ID 44 es "FA WSL" (Inglaterra, fútbol femenino)** — un dato incorrecto de la investigación previa. Se hizo `GET /leagues?country=Argentina` contra la API real y se confirmó el ID correcto:

**League ID correcto: 128 — "Liga Profesional Argentina".** Temporada vigente al 2026-09-19: `season=2026` (2026-01-22 a 2026-11-08), con cobertura confirmada de fixtures/eventos/alineaciones/estadísticas y odds; lesiones sin cobertura confirmada para la temporada 2026 (sí la tuvo 2025 — monitorear si mejora).

Lección aplicada: ningún ID/endpoint reportado por investigación web se usa en código sin verificarse primero contra una llamada real a la API (ver `backend/app/external/api_football.py` y su test de smoke). Este es exactamente el tipo de error que ADR-0007/CLAUDE.md buscan prevenir mediante verificación, no confianza ciega en fuentes de segunda mano.

## Hallazgo crítico: el plan Free NO cubre la temporada en curso (2026-09-19)

Al probar `GET /fixtures?league=128&season=2026` (y `season=2025`) con la cuenta Free real, la API devuelve explícitamente: `"Free plans do not have access to this season, try from 2022 to 2024."` — verificado con las 4 temporadas: **2022 ✅, 2023 ✅, 2024 ✅, 2025 ❌, 2026 (actual) ❌**. No es un límite de requests/día — es una restricción dura por plan, independiente de cuántos requests queden disponibles.

**Implicancia directa para el roadmap:**
- Las Fases 2-6 (ingesta histórica, features, baselines, backtesting/calibración) son **totalmente viables con el plan Free**, y de hecho mejor de lo esperado: 3 temporadas completas (2022-2024) con eventos/alineaciones/estadísticas, a costo $0.
- La Fase 7 (automatización T-72/T-24/T-2 sobre partidos reales de la temporada 2026) **no es viable con el plan Free bajo ninguna circunstancia** — no es cuestión de esperar a acumular más requests, hay que pasar a un plan pago antes de llegar a esa fase.
- No se confirmó documentalmente (el sitio de API-Football bloquea scraping/fetch automatizado con 403) si el plan Pro ($19/mes) desbloquea la temporada actual o si hace falta un tier superior — **se debe verificar esto empíricamente contratando el plan más barato una vez que el proyecto llegue a Fase 7**, no antes, y no asumirlo de la documentación de marketing.

Esto se comunicó al usuario como un hallazgo temprano (no bloquea Fase 2, sí es una decisión de gasto pendiente para cuando el roadmap llegue a Fase 7).

## Actualización (2026-09-19, Fase 6): el usuario contrató el plan Pro — confirmado que SÍ desbloquea la temporada actual

El usuario decidió por su cuenta pagar el plan Pro de API-Football ($19/mes, dentro del presupuesto de $30/mes) para poder avanzar con la Fase 6 sin esperar ~14 días de backfill de alineaciones al ritmo del free tier (100 req/día vs. 7500 req/día en Pro).

Verificado empíricamente (no asumido de la documentación de marketing, que el 403 de scraping nunca permitió confirmar): con el plan Pro activo, `GET /fixtures?league=128&season=2025` y `season=2026` **ya no devuelven el error de plan** — 510 fixtures en 2025, 495 en 2026 (temporada en curso). Esto resuelve la incertidumbre que ADR-0003 dejó abierta sobre si Pro desbloquea la temporada actual: **sí lo hace**. Fecha de vencimiento de la suscripción: 2026-10-20 (mensual, requiere renovación).

Consecuencia práctica: la Fase 7 (automatización T-72/T-24/T-2 sobre partidos reales) ya no está bloqueada por falta de acceso a datos de temporada actual — el bloqueo que quedó documentado arriba ("no es viable con el plan Free bajo ninguna circunstancia") queda resuelto ahora que el plan es Pro. Se aprovecha además para extender el histórico de entrenamiento/evaluación con las temporadas 2025 y 2026 (parcial, solo partidos ya jugados) — más datos para los folds de walk-forward de ADR-0007/ADR-0010, que hasta ahora dependían de una muestra chica de 3 temporadas.

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
