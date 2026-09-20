# Documento Maestro de Arquitectura V1
## Sistema Multiagente de Pronósticos Probabilísticos de Fútbol — Primera División Argentina

**Fecha original:** 2026-09-19
**Estado:** Aprobado y en ejecución — Fase 6 en curso (ver `docs/roadmap/ROADMAP.md` para el estado real de cada fase). Las decisiones de Sección P ya fueron tomadas; se conserva esa sección como registro histórico, no como pendiente.

Este documento consolida la visión del producto (brief original del usuario) en una arquitectura concreta, tal como se aprobó al inicio del proyecto. **No se reescribe con cada fase completada** — los ADRs (`docs/adr/`) son la fuente de verdad cuando haya cualquier discrepancia entre este documento y el estado real del código, y `docs/data/schema.md` es la fuente de verdad para el esquema (distingue explícitamente implementado vs. diseñado-no-implementado). Este documento describe la visión y el porqué; para "qué existe hoy", preferir siempre ADRs + schema.md + código sobre este archivo.

---

## A. Evaluación de viabilidad

| Elemento del brief | Viabilidad |
|---|---|
| Predicción 1-X-2 interna + normalización pública sin empate | **Viable ahora**, es aritmética simple sobre probabilidades ya calculadas (Sección 5). |
| 3 snapshots por partido (T-72/T-24/T-2) | **Viable ahora** con GitHub Actions (ADR-0002); depende de que las fuentes de datos actualicen con suficiente frecuencia cerca del kickoff. |
| Modelo probabilístico reproducible (Poisson/Dixon-Coles/Elo) | **Viable ahora**, técnicas estándar y bien documentadas, no requiere datos exóticos. |
| Datos cualitativos estructurados (lesiones, rotaciones) | **Difícil al inicio**: requiere que Football Intelligence Agent construya buena cobertura manualmente al principio; se simplifica una vez que API-Football provea lesiones/alineaciones de forma consistente. |
| Benchmark contra bookmakers | **Parcialmente incierto**: no se confirmó si The Odds API cubre Liga Profesional Argentina (ADR-0003) — a verificar en Fase 0/1. |
| Backtesting con validación temporal estricta | **Viable pero exige disciplina de ingeniería** (ADR-0007) — es la parte donde más fácil es cometer errores silenciosos (leakage), por eso tiene su propio agente independiente. |
| Presupuesto ≤ USD 30/mes | **Viable**: la combinación elegida (ADR-0002 + ADR-0003) cuesta $0-4/mes en hosting y $0/mes en datos para el arranque, dejando margen amplio. |
| Expansión internacional futura | **Viable en el diseño** (esquema con `competitions`/`external_ids` desacoplado, ADR data model), pero **potencialmente cara** al escalar: ligas europeas de calidad en APIs gratuitas son más limitadas que Argentina en algunos proveedores (ej. football-data.org sí cubre top-5 europeas gratis, al revés que para Argentina) — se reevaluará fuente por liga en su momento (Sección 25 del brief).
| Head-to-head como feature | **Potencialmente innecesario** — el brief mismo advierte no asumir que aporta señal; se tratará como candidato a testear y descartar en Fase 6, no como feature garantizada. |

## B. Arquitectura multiagente

Ver ADR-0005 para el razonamiento completo de consolidación (de 10+1 roles propuestos a 7+1). Diagrama textual:

```
                          ┌─────────────────────────┐
                          │   ORQUESTADOR / CTO      │
                          │ (sesión principal Claude,│
                          │  guiada por CLAUDE.md)   │
                          └────────────┬─────────────┘
                                       │ delega / coordina / aprueba
        ┌──────────────┬──────────────┼──────────────┬──────────────┬──────────────┐
        │              │              │              │              │              │
        ▼              ▼              ▼              ▼              ▼              ▼
┌───────────────┐┌─────────────┐┌────────────┐┌─────────────┐┌────────────┐┌─────────────┐
│ Data & Backend││  Football   ││ Modeling & ││ Evaluation & ││ Frontend/  ││   QA & Data ││ DevOps/
│   Platform    ││ Intelligence││  Feature   ││ Calibration  ││  Product   ││  Integrity  ││  MLOps
│               ││             ││ Engineering││ (independiente││            ││ (revisa todo││
│ conectores,   ││ señales     ││            ││  de Modeling)││ Next.js UI ││  lo demás)  ││ scheduling,
│ BD, API       ││ cualitativas││ features + ││ backtesting, ││            ││             ││ deploy,
│               ││ jerarquía   ││ modelos    ││ calibración, ││            ││             ││ alertas
│               ││ de fuentes  ││ (Elo→      ││ promoción/   ││            ││             ││
│               ││             ││ Poisson→...││ rechazo      ││            ││             ││
└───────┬───────┘└──────┬──────┘└──────┬─────┘└──────┬───────┘└─────┬──────┘└──────┬──────┘└──────┬──────┘
        │               │              │             │              │              │              │
        └───────────────┴──────────────┴─────────────┴──────────────┴──────────────┴──────────────┘
                                    todos escriben/leen vía contratos
                                    estructurados (JSON Schema) — ver Sección 17 del brief
```

Detalle completo de cada agente (misión, responsabilidades, límites, inputs/outputs, herramientas, dependencias, criterios de escalación) en `.claude/agents/*.md`.

## C. Arquitectura completa del sistema (flujo de datos)

```
FUENTES EXTERNAS                 INGESTIÓN              ALMACENAMIENTO
┌────────────────┐        ┌──────────────────┐   ┌─────────────────────────┐
│ API-Football    │───────▶│ Data & Backend    │──▶│ PostgreSQL (Neon)        │
│ (fixtures,      │        │ Platform Agent    │   │ competitions, seasons,   │
│ resultados,     │        │ (conectores +     │   │ teams, matches,          │
│ lineups,        │        │  validación)      │   │ match_stats,             │
│ lesiones)       │        └──────────────────┘   │ player_availability,     │
├─────────────────┤                                │ news_signals,            │
│ rhinoah/futbol- │───────▶ (bootstrap histórico) │ data_sources             │
│ argentino-data  │                                └────────────┬────────────┘
├─────────────────┤                                             │
│ Noticias/prensa │───────▶ Football Intelligence Agent ─────────┤
│ (jerarquía de   │        (estructura señales cualitativas)     │
│ fuentes)        │                                             │
├─────────────────┤                                             ▼
│ The Odds API    │──────▶ bookmaker_snapshots (solo benchmark, nunca feature)
└─────────────────┘                                             │
                                                                 ▼
                                              PROCESAMIENTO / FEATURES
                                    ┌──────────────────────────────────┐
                                    │ Modeling & Feature Engineering    │
                                    │ Agent: build_features(match_id,   │
                                    │ as_of_timestamp) → feature_snapshots │
                                    └────────────────┬──────────────────┘
                                                      ▼
                                              MODELOS (ADR-0006)
                                    ┌──────────────────────────────────┐
                                    │ Baseline 0 (ingenuo) → Baseline 1 │
                                    │ (Elo) → Baseline 2 (Poisson/      │
                                    │ Dixon-Coles) → candidatos (logit, │
                                    │ GBM) → model_versions             │
                                    └────────────────┬──────────────────┘
                                                      ▼
                                           CALIBRACIÓN Y EVALUACIÓN
                                    ┌──────────────────────────────────┐
                                    │ Evaluation & Calibration Agent:   │
                                    │ walk-forward validation, log loss,│
                                    │ Brier, ECE → evaluation_metrics   │
                                    │ → promoción/rechazo a producción  │
                                    └────────────────┬──────────────────┘
                                                      ▼
                                    PREDICCIONES Y SNAPSHOTS (append-only)
                                    ┌──────────────────────────────────┐
                                    │ prediction_runs (T-72/T-24/T-2,   │
                                    │ disparados por GitHub Actions) →  │
                                    │ predictions (prob 1-X-2 + pública)│
                                    └────────────────┬──────────────────┘
                                                      ▼
                                              API (FastAPI, Render)
                                                      ▼
                                          FRONTEND (Next.js, Vercel)
                                    próximos partidos · partido individual
                                    con evolución 72h/24h/2h · disputados
                                                      ▼
                                    RESULTADOS REALES → results → feedback
                                    a evaluation_metrics (ciclo de mejora)
```

## D. Stack tecnológico (decisión final, no solo alternativas)

| Componente | Elección | ADR |
|---|---|---|
| Backend/API | Python 3.12 + FastAPI | ADR-0004 |
| Modelado/pipelines | Python (pandas, scikit-learn, statsmodels; lightgbm como candidato de 2ª etapa) | ADR-0004, ADR-0006 |
| Base de datos | PostgreSQL gestionado en **Neon** (free tier) | ADR-0002 |
| Frontend | Next.js en **Vercel** (free tier) | ADR-0004 |
| Backend hosting | **Render** (free web service) | ADR-0002 |
| Scheduling (T-72/T-24/T-2) | **GitHub Actions** (`schedule:`), repo público | ADR-0002 |
| Experiment tracking | Registro estructurado en BD (`model_versions`), sin herramienta externa por ahora | ADR-0004 |

## E. Investigación de fuentes de datos

Ver ADR-0003 para la tabla comparativa completa con URLs y fechas de consulta (2026-09-19). Resumen de la decisión:

- **Fixtures/resultados/alineaciones/lesiones:** API-Football, free tier (100 req/día).
- **Bootstrap histórico:** dataset abierto `rhinoah/futbol-argentino-data` (GitHub, gratis).
- **Benchmark de cuotas:** The Odds API, free tier — **pendiente confirmar** cobertura de Liga Profesional Argentina antes de construir el módulo.
- **Descartados como dependencia automatizada:** football-data.org (no cubre Argentina gratis), Sportmonks (cobertura de Argentina no confirmada en plan barato), SofaScore y FBref (ToS prohíbe/no soporta scraping automatizado), Promiedos (sin API oficial, sin histórico).
- **Costo:** el free tier de API-Football bloqueaba por completo las temporadas 2025/2026 (verificado con llamadas reales a la API, no documentación) — el usuario aprobó el upgrade a **API-Football Pro ($19/mes, 7500 req/día)**, activo desde 2026-09-19 (ADR-0003). Ya no es una reserva hipotética; es el gasto real actual, dentro del techo de $30/mes.

## F. Estrategia de datos

Ver `docs/data/schema.md` para el esquema completo y actualizado — distingue explícitamente qué está implementado con migración aplicada (`competitions`, `seasons`, `teams`, `players`, `matches`, `results`, `match_lineups`, `feature_snapshots`, `model_versions`, `evaluation_metrics`) de lo diseñado pero deferido con trigger explícito (`predictions`, `prediction_runs`, `bookmaker_snapshots`, `player_availability`, `news_signals`, `data_sources`, `match_stats`, entre otros — ver ADR-0013/0014). La lista original de este documento (más abajo, sin cambios respecto a la propuesta inicial) describe la visión completa; no todas esas tablas existen todavía.

Principios clave: snapshots inmutables append-only (ADR-0008), features versionadas como JSONB mientras se experimenta, `external_ids` como jsonb para permitir múltiples proveedores por entidad sin romper el esquema al agregar competiciones (Sección 4 del brief).

## G. Estrategia de modelado

Ver ADR-0006. Orden obligatorio: Baseline 0 (ingenuo) → Baseline 1 (Elo + home advantage) → Baseline 2 (Poisson/Dixon-Coles) → candidato regresión logística multinomial → candidato GBM calibrado (solo si hay techo de rendimiento) → ensemble (solo si demuestra mejora empírica). Deep learning explícitamente descartado para V1. Ningún modelo se selecciona como final antes de pasar por Evaluation & Calibration Agent.

**Estado real (Fase 6, en curso):** baseline ingenuo, Elo+home advantage y Poisson/Dixon-Coles ya están implementados y entrenados sobre datos reales (2022-2026); el candidato de regresión logística multinomial está en experimentación activa. Ningún modelo fue promovido a `production` todavía — no existe pipeline de predicción en vivo (eso es Fase 7-8). Ver ADR-0011 para resultados concretos del candidato logístico.

**Visión de largo plazo (ADR-0009, no implementada todavía):** los baselines de la Fase 4 son el punto de partida, no el motor final. El objetivo declarado del producto es un sistema que combine progresivamente múltiples familias de modelos (estadísticos, ratings, ML clásico, bayesianos jerárquicos, temporales, xG-based, redes neuronales si el volumen de datos lo justifica) bajo un meta-modelo/ensemble con gating dinámico, operado con un esquema Champion/Challenger y un ciclo de aprendizaje continuo controlado (walk-forward, holdout intocado, tamaño mínimo de muestra, rollback inmediato, auditoría de cada promoción/rechazo). ADR-0009 fija los principios no negociables de esa evolución — en particular, que las predicciones de terceros (incluido el endpoint `predictions` de API-Football) nunca sustituyen al motor propio ni se usan como feature, salvo benchmarking explícito. El roadmap (Sección O) sigue mandando el orden real de implementación; esta visión solo restringe cómo se diseña lo que se construye ahora para no reconstruirlo después.

## H. Estrategia de evaluación

Ver ADR-0007. Métricas en orden de prioridad: Log Loss (principal) → Brier Score → calibration curves/ECE → accuracy (secundaria, nunca criterio de promoción). Validación exclusivamente temporal (walk-forward/expanding window). Comparación obligatoria contra 4 referencias: baseline ingenuo, baseline de fuerza histórica, modelo candidato, consenso bookmaker (cuando sea temporalmente comparable). Promoción de modelo requiere mejora consistente, documentada en ADR, evaluada por un agente distinto al que entrenó.

## I. Diseño del pipeline T-72/T-24/T-2

**No implementado todavía (Fase 7-8) — esto es el diseño objetivo, no el estado actual.** Hoy no existen `predictions`/`prediction_runs` en el esquema ni workflows que los generen (ver `docs/data/schema.md`, sección "diseñado, no implementado").

Tres workflows de GitHub Actions independientes, cada uno:
1. Consulta partidos cuyo `kickoff_at` cae dentro de la ventana del horizonte correspondiente.
2. Dispara `build_features(match_id, as_of_timestamp=now())` respetando el corte temporal.
3. Ejecuta el modelo en producción (`model_versions.status = 'production'`) sobre esos features.
4. Inserta una nueva fila en `predictions` (nunca actualiza una existente).
5. Un cuarto workflow, disparado post-kickoff, registra `results` cuando el resultado está disponible.

Nota del brief (Sección 6): si alguna liga publica alineaciones confirmadas más cerca del kickoff que 2h, se documentará como hallazgo y se evaluará agregar un 4º snapshot solo si los datos demuestran que mejora las predicciones — no se cambia el intervalo por defecto.

## J. Seguridad contra leakage

Checklist completo en ADR-0007, resumen de riesgos concretos y controles:

| Riesgo | Control |
|---|---|
| Feature calculado con datos posteriores al horizonte del snapshot | `build_features` recibe `as_of_timestamp` explícito y filtra toda consulta por ese corte |
| Dato corregido retroactivamente usado para reconstruir el pasado | Snapshots inmutables (ADR-0008); no se recalculan features históricos con datos "corregidos" después |
| Split aleatorio de partidos en entrenamiento/test | Prohibido por política (ADR-0007); solo walk-forward/expanding window |
| Selección de hiperparámetros con el mismo holdout del reporte final | Holdout de un solo uso, separado de la validación usada para seleccionar |
| Resultado usado para "ayudar" a una predicción del mismo partido | `results` nunca es input de `build_features` para ese mismo `match_id` antes del kickoff |

## K. Modelo de datos

Ver `docs/data/schema.md` (detalle completo). Tablas explícitamente excluidas en V1 por simplicidad: autenticación/usuarios, apuestas/bankroll (módulo futuro separado).

## L. Interfaz MVP

Páginas mínimas (Frontend/Product Agent, ver `.claude/agents/frontend-product.md`):
1. **Próximos partidos** — listado por fecha/competición.
2. **Partido individual** — `Equipo A XX% — Equipo B YY%`, fecha de actualización, evolución 72h/24h/2h.
3. **Partidos disputados** — con resultado real.

Sin dashboards complejos en V1 (Sección 20 del brief) — prioridad es confiabilidad del motor, no superficie de producto.

## M. Costes

**Estado real (2026-09-20):** el escenario que se ejecuta hoy es el de la columna "MVP recomendado" — el free tier de API-Football resultó insuficiente (bloqueaba temporadas 2025/2026 por completo) y el usuario aprobó el upgrade a Pro.

| Categoría | MVP gratuito (proyectado inicialmente) | Gasto real actual |
|---|---|---|
| Frontend (Vercel) | $0 | $0 |
| Backend (Render free) | $0 | $0 |
| Base de datos (Neon free) | $0 | $0 |
| Scheduling (GitHub Actions, repo público) | $0 | $0 |
| Datos (API-Football) | $0 (free) | **$19/mes (Pro, activo desde 2026-09-19, ADR-0003)** |
| Benchmark de odds (The Odds API free) | $0 | $0 (módulo no construido todavía) |
| **Total** | **$0/mes** | **$19/mes**, dentro del límite de $30/mes |

## N. Riesgos (registro priorizado)

| # | Riesgo | Impacto | Probabilidad | Mitigación |
|---|---|---|---|---|
| 1 | Data leakage silencioso en pipelines de features/backtesting | Alto — invalida toda la credibilidad estadística del producto | Media | Checklist obligatorio + agente QA independiente (ADR-0007) |
| 2 | Límite de 100 req/día de API-Football insuficiente cerca de fechas con muchos partidos | Medio | Media-Alta | Monitoreo de consumo (DevOps/MLOps Agent) + reserva de upgrade a $19/mes aprobado de antemano por el usuario |
| 3 | The Odds API no cubre Liga Profesional Argentina | Bajo (afecta solo benchmark, no el modelo) | Media | Verificar en Fase 0/1 antes de construir el módulo; documentar como no disponible si no cubre |
| 4 | Cold starts en Render free degradan experiencia si el tráfico crece | Bajo en MVP, medio si hay usuarios reales | Alta (por diseño del free tier) | Aceptado explícitamente para MVP (ADR-0002); revisar antes de cualquier lanzamiento público con tráfico real |
| 5 | Volumen de datos supera el free tier de Neon (0.5GB) al crecer histórico/ligas | Bajo en el corto plazo | Baja en V1, Media al expandir | Trigger de revisión documentado en ADR-0002 |
| 6 | Features cualitativas (lesiones/rotaciones) con cobertura insuficiente al inicio | Medio — puede degradar la calidad de T-24/T-2 | Alta al inicio | Football Intelligence Agent con jerarquía de fuentes explícita; se documenta la limitación, no se inventa el dato faltante |
| 7 | Sobreajuste con modelos complejos dado el tamaño de dataset de una sola liga | Medio | Media si se salta el orden de ADR-0006 | Orden de complejidad incremental obligatorio + validación temporal estricta |
| 8 | Repo público expone lógica de negocio | Bajo (no hay ventaja competitiva por ocultar metodología en el MVP) | N/A | Aceptado; revisar si en el futuro hay razón comercial para privacidad |

## O. Roadmap

Ver `docs/roadmap/ROADMAP.md` para el detalle completo de las 11 fases (0-10), cada una con objetivo, tareas, agente responsable, entregables, tests y criterio de finalización.

## P. Decisiones que requieren la intervención del usuario

**Resueltas (2026-09-19):**

1. ✅ **Documento maestro y ADRs 0001-0008 aprobados** — se avanza a Fase 1.
2. ✅ **Repositorio público en GitHub** — confirmado por el usuario. GitHub Actions corre los schedules gratis sin necesidad de GitHub Pro. Nunca se commitean credenciales ni datos sensibles (van en variables de entorno, `.env` gitignored).
3. ✅ **Upgrades pagos: consultar siempre antes de contratar** — el usuario prefiere aprobar caso por caso, no pre-autorizar. Si el free tier de API-Football (100 req/día) resulta insuficiente, DevOps/MLOps Agent lo detecta y lo escala al usuario antes de contratar el plan Pro ($19/mes) — nunca se contrata automáticamente.

**Resueltas después del inicio:**

4. ✅ **Cuenta/API key de API-Football**: creada por el usuario, rotada una vez (ADR-0016, incidente de credenciales) y de nuevo activa. Upgrade a plan Pro ($19/mes) aprobado explícitamente por el usuario el 2026-09-19 (ADR-0003) tras confirmar que el free tier bloqueaba las temporadas en curso.
5. ✅ **Nombre del producto**: decidido por el usuario — **"FulbolAI"** (ADR-0017), no "Sistema Multiagente de Pronósticos de Fútbol" como en los documentos iniciales.

**Pendientes / acción del usuario (no bloquean el trabajo en curso):**

6. **Dominio propio** (en vez del subdominio gratuito de Vercel): tiene costo (~$10-15/año) y es una preferencia de producto sin urgencia — se puede decidir más adelante, no bloquea ninguna fase.

Todo lo demás (stack técnico, esquema de datos, arquitectura de agentes, estrategia de modelado y evaluación, orden de fases) fue decidido como parte de esta responsabilidad de CTO y está documentado y justificado en los ADRs — no requiere aprobación técnica línea por línea, pero está abierto a que se cuestione si algo no convence.
