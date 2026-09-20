# ADR-0012 — Scheduling de T-72/T-24/T-2: dispatcher periódico, no 3 cron jobs exactos

**Estado:** Aceptada — corrige el diseño de ADR-0002 antes de construir Fase 7 (todavía no implementada)
**Fecha:** 2026-09-20
**Decide:** CTO/Orquestador (Claude), a partir de una revisión externa (ChatGPT, vía el usuario) con mérito técnico real

## Contexto

ADR-0002 diseñó originalmente el scheduling de los snapshots T-72h/T-24h/T-2h como 3 workflows de GitHub Actions con `cron:` apuntando a horarios "exactos" por partido. Una revisión externa señaló un riesgo operacional real: **GitHub documenta explícitamente que los workflows programados (`schedule:`) pueden demorarse bajo carga, y jobs en cola pueden descartarse** — aceptable para CI, nightly jobs o reportes, pero riesgoso como única fuente de verdad de "este partido necesita su predicción T-2 ahora".

Como todavía no se implementó Fase 7 (automatización en vivo), corregir esto ahora es gratis — evita construirlo mal y tener que rehacerlo, que es exactamente el problema que este proyecto busca evitar en general (ver CLAUDE.md, ADR-0009).

## Decisión

Reemplazar "3 cron jobs de horario exacto" por un **dispatcher periódico + tabla de trabajo**:

1. Un solo workflow de GitHub Actions corre cada 5 minutos (`schedule: cron: "*/5 * * * *"`), gratis en un repo público (ADR-0002 no cambia en esto).
2. Ese workflow no contiene lógica de negocio — solo invoca un dispatcher (Python) que hace `SELECT` sobre una tabla de trabajos pendientes filtrando `scheduled_for <= now() AND status = 'pending'`.
3. Los trabajos (`prediction_jobs`, o el nombre que se defina al implementarlo) se generan de antemano a partir de `matches.kickoff_at` (uno por horizonte por partido: `kickoff_at - 72h`, `kickoff_at - 24h`, `kickoff_at - 2h`).
4. El dispatcher marca cada trabajo tomado con un lock/idempotencia (ej. `status = 'processing'`, o un `claimed_at` con expiración) antes de ejecutar el pipeline de predicción correspondiente, para que dos corridas del dispatcher no dupliquen trabajo si se superponen.
5. Si una corrida del dispatcher se retrasa o se salta (GitHub Actions bajo carga), la corrida siguiente (a los 5 minutos) recoge el trabajo pendiente — el estado vive en Postgres, no en que el cron dispare exactamente a la hora esperada. Esto es lo que resuelve el riesgo que motiva esta ADR: no necesitamos que el disparador sea preciso, solo que sea frecuente y el trabajo sea recuperable.

GitHub Actions sigue siendo la herramienta correcta para CI/CD, evaluación nocturna, reportes y mantenimiento — el cambio es específicamente sobre no depender de su precisión de horario para la lógica de negocio sensible al tiempo.

## Consecuencias

- Positivas: tolerante a demoras/fallas del propio scheduler sin perder ni duplicar trabajo; sigue costando $0; la lógica de negocio ("qué predicción generar y cuándo") queda en código/datos propios, testeable, en vez de en la configuración de un cron externo.
- Negativas: requiere una tabla de trabajos + lógica de dispatcher que no existiría con 3 cron jobs simples — algo más de código a mantener, pero acotado y ya justificado por el riesgo documentado de GitHub.
- Trigger de revisión: si en el futuro el volumen de partidos simultáneos crece mucho (múltiples ligas en el mismo horario), reevaluar si 5 minutos de granularidad sigue siendo suficiente para T-2 (podría necesitar bajar a 1-2 minutos, todavía dentro de límites gratuitos de GitHub Actions en un repo público).

## Fuentes

Documentación de GitHub sobre limitaciones de `schedule:` en Actions (demoras bajo carga, jobs descartados) — referenciada por la revisión externa; no se volvió a verificar la URL exacta en esta ADR, pero el comportamiento descrito es consistente con el comportamiento documentado y ampliamente conocido de GitHub Actions `schedule` events. Si se requiere la cita exacta antes de implementar Fase 7, verificar en la documentación oficial de GitHub Actions en ese momento (las políticas pueden cambiar).
