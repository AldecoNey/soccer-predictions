# ADR-0004 — Lenguajes y frameworks de la aplicación

**Estado:** Aceptada
**Fecha:** 2026-09-19
**Decide:** CTO/Orquestador (Claude)

## Contexto

Necesitamos elegir lenguaje/framework de backend, de frontend y el enfoque de la capa de datos/ML, optimizando para: bajo costo de mantenimiento, ecosistema maduro de librerías estadísticas/ML, velocidad de desarrollo asistido por agentes, y que el usuario (nivel técnico básico) no tenga que tocar código directamente salvo revisar resultados.

## Decisión

- **Backend / API:** Python 3.12 + **FastAPI**. Razón: Python es el estándar de facto para modelado estadístico/ML (pandas, scikit-learn, statsmodels, scipy), lo que evita duplicar lógica en dos lenguajes distintos entre "el modelo" y "la API que lo sirve". FastAPI da validación automática vía Pydantic (clave para los contratos JSON entre agentes, ver ADR-0005) y documentación OpenAPI gratis.
- **Pipelines de datos y modelado:** Python, con `pandas`/`polars` para transformación, `scikit-learn` + `statsmodels` para baselines, `lightgbm` reservado como candidato de segunda etapa (ver ADR-0006). Sin frameworks de deep learning (no justificado, ver ADR-0006).
- **Base de datos:** PostgreSQL (motor gestionado: Neon, ver ADR-0002). Relacional porque el dominio es fuertemente relacional (equipos, partidos, temporadas, snapshots con integridad referencial) y necesitamos transacciones e integridad fuerte para evitar corromper el historial de predicciones.
- **Frontend:** **Next.js** (React) en Vercel. Razón: despliegue gratuito trivial, soporta tanto páginas estáticas (rápidas, baratas) como rutas dinámicas si más adelante se necesitan cuentas de usuario; ecosistema amplio si en el futuro se contrata a un desarrollador frontend externo.
- **Scheduling/automatización:** GitHub Actions (ver ADR-0002) invocando scripts Python empaquetados como CLI (no servicios "always-on"), lo que mantiene el costo en $0 y hace cada ejecución auditable como un log de workflow.
- **Experiment tracking (modelos):** empezar con registros estructurados en la propia base de datos (tabla `model_versions` + artefactos versionados por hash de git commit) en vez de una herramienta externa como MLflow. Justificación: a la escala del MVP (una liga, pocos modelos candidatos), una herramienta dedicada es sobre-ingeniería; se reevaluará si el número de experimentos crece mucho.

## Opciones descartadas

- **Node.js/TypeScript de punta a punta:** descartado porque el ecosistema de modelado estadístico/probabilístico maduro está en Python, y dividir la lógica entre dos runtimes añade complejidad sin beneficio real para este dominio.
- **R para modelado:** ecosistema estadístico excelente, pero peor integración con APIs web modernas y con el resto del stack; Python cubre las mismas técnicas (Poisson, Dixon-Coles, GLMs) sin ese costo de integración.
- **Deep learning frameworks (PyTorch/TensorFlow):** no justificados en el MVP (ver ADR-0006, principio de "empezar simple, escalar solo si se demuestra mejora").

## Consecuencias

- Positivas: un solo lenguaje (Python) cubre backend, pipelines y modelado, reduciendo superficie de mantenimiento para un equipo mayormente agéntico.
- Negativas: Next.js introduce un segundo lenguaje (TypeScript/JavaScript) solo para la capa de presentación; se acepta porque el frontend es deliberadamente simple en el MVP (Sección 20 del brief original).
- Trigger de revisión: si se requiere frontend nativo móvil, o si el volumen de tráfico exige backend en un lenguaje más performante que Python.

## Fuentes

Decisión basada en conocimiento consolidado del ecosistema (FastAPI, pandas, scikit-learn, Next.js, Vercel son estándares ampliamente documentados); no requiere verificación de pricing adicional a la ya hecha en ADR-0002.
