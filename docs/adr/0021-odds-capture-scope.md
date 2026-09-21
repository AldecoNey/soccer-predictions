# ADR-0021 — Captura mínima de cuotas: proveedor y alcance

**Estado:** Aceptada
**Fecha:** 2026-09-21
**Decide:** CTO/Orquestador (Claude), con confirmación del usuario sobre el alcance

## Contexto

ADR-0003 dejó pendiente confirmar si algún proveedor cubre cuotas de Liga Profesional Argentina. Al retomar la discusión del "capturador prospectivo mínimo" (propuesta de una revisión externa, evaluada y parcialmente adoptada en ADR-0018), se investigaron dos vías en paralelo: The Odds API (proveedor nuevo) y el endpoint `/odds` de API-Football (proveedor ya contratado, Pro, $19/mes desde ADR-0003).

Restricción de presupuesto: $30/mes total, ~$19/mes ya comprometidos a API-Football Pro — cualquier proveedor nuevo compite por los ~$11/mes restantes.

## Opciones consideradas

1. **The Odds API** — confirmado que cubre "Primera División - Argentina" (`soccer_argentina_primera_division`), verificado en vivo el 2026-09-21 contra su página de cobertura y precios. Free tier: 500 créditos/mes, costo por request variable (`markets × regions`). Tiers pagos arrancan en $30/mes — por sí solo ya excede el margen de presupuesto restante. Requeriría alta de cuenta y una segunda credencial a gestionar.
2. **Endpoint `/odds` de API-Football** (elegida) — probado en vivo el 2026-09-21 contra el fixture real de hoy (Aldosivi vs Atlético Tucumán, `fixture=1493137`): devuelve cuotas reales y actuales de múltiples bookmakers (ej. William Hill: Local 3.10 / Empate 2.88 / Visitante 2.40, mercado "Match Winner"), con `update` timestamp del proveedor. **Costo incremental: $0** — ya es parte del plan Pro contratado. Sin credencial nueva, sin cuenta nueva.

Con el proveedor ya pago cubriendo la liga con datos reales verificados, no se justifica sumar The Odds API — sería pagar de nuevo por algo que ya se tiene.

## Decisión

**Usar el endpoint `/odds` de API-Football, capturado solo para el mercado "Match Winner" (1X2)** — no se capturan mercados adicionales (over/under, hándicap, marcador exacto, etc.); no aportan al benchmark que exige ADR-0007 (comparación contra consenso de mercado en 1-X-2) y solo agregarían volumen de datos sin propósito.

**Alcance deliberadamente recortado respecto a la propuesta original de "cuotas + alineaciones":** se descarta la mitad de "alineaciones" del capturador prospectivo. Motivo: ADR-0011 (completada horas antes de esta discusión) ya demostró que `rotation_index` no tiene poder predictivo **ni siquiera con acceso de oráculo** a la alineación real. Invertir en sondeo activo para capturar el momento exacto de confirmación de alineaciones — que es estrictamente más difícil de obtener que la alineación final (ya recuperable retroactivamente, ver `match_lineups`) — no tiene justificación mientras la señal que dependería de ese dato ya se descartó. Se verificó en vivo (2026-09-21, sondeo cada 3 min desde ~1h54 antes del kickoff de Aldosivi vs Atlético Tucumán hasta el resultado) que las alineaciones se confirmaron recién a **T-12 minutos** del kickoff — un solo dato empírico, no una constante asumida para toda la liga/proveedor, pero suficiente para confirmar que un snapshot T-2 (2 horas) no las habría capturado, y que obtenerlas exige sondeo activo repetido, no una sola consulta. Refuerza con un número concreto que es la parte cara de la propuesta original, ahora sin contrapartida de valor.

**Cadencia: manual/bajo demanda por ahora, no automatizada.** Se construye el pipeline de captura (`pipelines/capture_odds_snapshot.py`) pero no se programa un GitHub Actions que lo dispare solo — eso es exactamente el trabajo de Fase 7 ("Automatización T-72/T-24/T-2"), y automatizarlo ahora adelantaría esa fase antes de que el roadmap llegue a ella (regla no negociable de CLAUDE.md). Lo que se gana capturando manualmente desde ya: cuotas reales para los partidos que se investiguen en el corto plazo no se pierden por no tener el pipeline completo todavía; lo que se evita: construir infraestructura de scheduling antes de tiempo.

## Consecuencias

- Positivas: benchmark de cuotas real disponible sin gasto nuevo ni credencial nueva; scope acotado a lo que ADR-0007 realmente necesita.
- Negativas / deuda técnica aceptada: captura manual significa que se pierden partidos si nadie corre el script cerca del kickoff — aceptable mientras no hay todavía un pipeline de predicciones en vivo que consuma estos datos de forma crítica (Fase 7-8 no empezaron).
- Trigger de revisión: (a) al llegar a Fase 7, decidir si este script se programa vía GitHub Actions o se reemplaza por algo más completo; (b) si en el futuro se reconsidera capturar timing de alineaciones, sería porque apareció una señal de rotación distinta con resultado positivo en backtesting — no porque "ya que estamos" se vuelva a agregar.

## Fuentes

- [The Odds API — cobertura de deportes](https://the-odds-api.com/sports-odds-data/sports-apis.html) — accedido 2026-09-21.
- [The Odds API — precios](https://the-odds-api.com/#get-access) — accedido 2026-09-21.
- Endpoint `/odds` de API-Football probado en vivo contra `fixture=1493137` (Aldosivi vs Atlético Tucumán, 2026-09-21) usando la key Pro ya activa del proyecto — respuesta real con cuotas de William Hill y otros bookmakers, no documentación de marketing.
- Endpoint `/fixtures/lineups` probado en vivo contra el mismo fixture a T-1h54min del kickoff — 0 alineaciones devueltas, confirmando que la confirmación ocurre más cerca del partido de lo que un snapshot T-2 alcanzaría a capturar con una sola consulta.
