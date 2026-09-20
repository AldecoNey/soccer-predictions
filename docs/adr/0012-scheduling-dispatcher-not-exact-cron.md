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

## Riesgo adicional encontrado al verificar (2026-09-20): auto-apagado a los 60 días

Verificado contra documentación oficial de GitHub (no asumido): **en repos públicos, GitHub deshabilita automáticamente cualquier workflow `schedule:` tras 60 días sin actividad en el repositorio** (push, release o PR mergeado — no cuenta que el propio workflow programado haya estado corriendo). Fuente: https://docs.github.com/actions/managing-workflow-runs/disabling-and-enabling-a-workflow (verificado 2026-09-20).

Esto es relevante para el dispatcher de esta ADR: si el proyecto llega a una fase estable donde pasan >60 días sin un commit (plausible una vez en producción, sin cambios de código frecuentes), **el dispatcher que genera las predicciones en vivo se apagaría solo**, silenciosamente, sin relación con la carga de partidos. No es un problema hoy (desarrollo activo), pero es un riesgo real a resolver antes de que el sistema dependa de correr desatendido por meses — opciones a evaluar cuando se implemente Fase 7: un commit trivial automatizado periódico, monitoreo externo que alerte si el dispatcher deja de correr, o mover el dispatcher a un host que no tenga esta política (fuera del alcance de este ADR, que sigue recomendando GitHub Actions para el MVP).

## Fuentes

- https://docs.github.com/actions/managing-workflow-runs/disabling-and-enabling-a-workflow (auto-apagado a 60 días, verificado 2026-09-20).
- La afirmación sobre demoras/descartes de `schedule:` bajo carga proviene de la revisión externa que motivó esta ADR y es consistente con el comportamiento ampliamente reportado de GitHub Actions, pero no se volvió a verificar contra una URL oficial específica en esta ADR — verificar antes de implementar Fase 7 si se necesita la cita exacta.
- La recomendación de evitar el minuto exacto de la hora (ej. `:00`) por congestión es comportamiento **reportado empíricamente por la comunidad, no documentación oficial de GitHub** — verificado explícitamente que no aparece en la documentación oficial de sintaxis de workflows (https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions, que solo documenta el mínimo de 5 minutos entre corridas). Se aplicó igual en `scheduled-hello-world.yml` por ser de costo cero y plausible, pero está etiquetado correctamente como práctica empírica, no como garantía de GitHub.
