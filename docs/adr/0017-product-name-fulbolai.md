# ADR-0017 — Nombre comercial: FulbolAI

**Estado:** Aceptada
**Fecha:** 2026-09-20
**Decide:** Usuario (decisión de producto — no técnica, fuera del alcance de lo que decido yo)

## Contexto

El usuario decidió el nombre comercial del producto: **FulbolAI**, eligiendo "fulbol" (pronunciación coloquial argentina de "fútbol") en vez de "futbol"/"fútbol" para reforzar la identidad local del proyecto.

## Decisión

- Nombre público/comercial: **FulbolAI**.
- El nombre interno de repositorio (`soccer-predictions`) y la descripción técnica ("Sistema Multiagente de Pronósticos de Fútbol") se mantienen como están por ahora — cambiar el nombre del repo de GitHub tiene costo (rompe la URL actual, hay que actualizar remotes) y no es necesario para que el nombre comercial exista; se evalúa un cambio de repo aparte, si el usuario lo pide explícitamente.
- La arquitectura multiagente sigue siendo un detalle interno/técnico — de cara al público, la propuesta de valor es la calidad y calibración de las predicciones, no la cantidad de agentes (alineado con una sugerencia de la misma revisión externa que motivó otras partes de esta ADR).
- Actualización de documentación pública (README, Master Architecture) con el nombre: se hace de forma incremental junto con la consolidación de documentación pendiente (ver ADR-0018), no como una reescritura completa ahora mismo.

## Consecuencias

- Positivas: nombre decidido, no bloquea nada técnico.
- Negativas: ninguna — es un cambio de nomenclatura, no de arquitectura.
- Trigger de revisión: si el usuario pide renombrar el repositorio de GitHub o comprar un dominio, eso sí requiere una decisión/acción explícita aparte (dominio implica gasto, ver CLAUDE.md sobre presupuesto).

## Fuentes

Decisión directa del usuario, 2026-09-20.
