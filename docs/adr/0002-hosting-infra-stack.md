# ADR-0002 — Stack de hosting e infraestructura MVP

**Estado:** Aceptada (revisar si cambian free tiers)
**Fecha:** 2026-09-19
**Decide:** CTO/Orquestador (Claude)

## Contexto

El MVP requiere: hosting de frontend (Next.js), hosting de backend (FastAPI), base de datos relacional persistente, y ejecución programada de pipelines 3 veces por partido (T-72h, T-24h, T-2h) más registro de resultados. Presupuesto total combinado (hosting + datos) ≤ USD 30/mes, con preferencia fuerte por free tier. Investigación de pricing actual realizada el 2026-09-19.

## Opciones consideradas (resumen; investigación completa disponible en el historial de research del proyecto)

| Servicio | Rol candidato | Free tier real | Limitación clave |
|---|---|---|---|
| Vercel (Hobby) | Frontend | Sí — 100GB transfer, 1M invocaciones | Cron jobs limitados a 1/día en Hobby → **no sirve** para T-72/T-24/T-2 |
| Railway | Backend/BD | No (solo trial $5/30 días) | Sin free tier permanente en 2026 → descartado |
| Render (free) | Backend | Sí — 750h/mes, cron nativo gratis | Postgres free se borra a los 30 días; web service duerme tras 15 min inactivo |
| Supabase (free) | BD | Sí — 500MB BD, 5GB egress | Proyecto se pausa tras 7 días sin requests (requiere keep-alive) |
| Neon (free) | BD | Sí — 100 CU-h/mes, autoscale a 0 | Sin pausa forzada tipo Supabase; límite de storage 0.5GB por proyecto |
| Fly.io | Backend/BD | No (solo trial) → descartado | Sin free tier en 2026 |
| GitHub Actions | Scheduling | Sí, ilimitado en repos públicos | En repos **privados** free, los workflows `schedule:` requieren GitHub Pro ($4/mes) |

## Decisión

- **Frontend:** Vercel (plan Hobby, gratis).
- **Backend (API FastAPI):** Render (free web service). Se acepta cold start (~1 min) porque el tráfico esperado del MVP es bajo y no hay SLA de latencia.
- **Base de datos:** Neon (free tier), no Supabase, específicamente porque Neon no pausa el proyecto por inactividad (Supabase sí, y requeriría un keep-alive artificial). Si en el futuro se necesita Auth/Storage integrado, se reevaluará Supabase vía un ADR nuevo.
- **Scheduling (T-72/T-24/T-2 + registro de resultados):** GitHub Actions con `schedule:` (cron), en un **repositorio público**. Justificación: es la única opción sin costo que garantiza ejecución confiable en el horario exacto, sin depender de que un servicio "esté despierto". El repo de código puede ser público sin riesgo porque no contendrá credenciales (ver `.env.example` y `.gitignore`); si más adelante se requiere privacidad de código, la alternativa es GitHub Pro (+$4/mes), lo cual es una decisión de producto, no técnica.

**Costo total de hosting estimado: $0–4/mes**, dejando prácticamente todo el presupuesto de $30/mes disponible para fuentes de datos.

## Consecuencias

- Positivas: MVP operable a costo ~$0 en infraestructura; todos los servicios elegidos soportan Python/FastAPI, Postgres estándar y Next.js sin lock-in fuerte (migración futura a Railway/AWS es directa vía `DATABASE_URL` estándar de Postgres).
- Negativas / deuda técnica aceptada: cold starts en Render free (aceptable para MVP, no para producción con usuarios reales — revisar antes de lanzamiento público); límite de 0.5GB en Neon free puede quedarse corto con varias temporadas históricas de múltiples ligas (aceptable para el alcance de Primera División Argentina del MVP).
- Trigger de revisión: si el volumen de datos supera ~400MB, si se necesita latencia consistente (sin cold start), o si el repo debe volverse privado por una fuente de datos con licencia restrictiva.

## Fuentes

- https://vercel.com/docs/limits (consultado 2026-09-19)
- https://vercel.com/docs/cron-jobs/usage-and-pricing (consultado 2026-09-19)
- https://railway.com/pricing (consultado 2026-09-19)
- https://docs.railway.com/pricing/plans (consultado 2026-09-19)
- https://neon.com/pricing (consultado 2026-09-19)
- https://docs.github.com/billing/managing-billing-for-github-actions/about-billing-for-github-actions (consultado 2026-09-19)
- Nota: algunos datos de Render/Supabase provienen de agregadores de terceros, no de la documentación oficial directamente; se recomienda reverificar en render.com/pricing y supabase.com/pricing antes de comprometerse si pasan varios meses antes de implementar.
