# ADR-0016 — Incidente de seguridad: exposición de `.env` vía ZIP a un tercero

**Estado:** Cerrado — credenciales rotadas y verificadas
**Fecha:** 2026-09-20
**Decide:** Usuario (acción) + CTO/Orquestador (Claude, verificación)

## Contexto

ADR previo (ver commit `7b3230b`) había verificado que `.env` **nunca llegó a git/GitHub** — eso seguía siendo cierto. Pero una revisión externa posterior planteó un vector distinto: el usuario había comprimido la carpeta del proyecto en su máquina para compartirla con ChatGPT como contexto de análisis. `.gitignore` protege contra commits a git; **no protege contra una compresión manual del directorio**, que incluye `.env` tal cual está en disco.

Se le preguntó directamente al usuario (no se asumió en ningún sentido): confirmó que el ZIP probablemente incluía `.env` con las credenciales reales (connection string de Neon, API key de API-Football).

## Decisión

Tratado como incidente real, no hipotético — rotación inmediata de ambas credenciales:

1. **Neon**: el usuario reseteó la contraseña del rol de base de datos desde la consola de Neon.
2. **API-Football**: el usuario regeneró la API key desde su dashboard.
3. `.env` local actualizado con ambos valores nuevos (nunca compartidos en el chat).

## Verificación

- `backend/scripts/check_db_connection.py` confirmó conexión exitosa con la nueva connection string (Postgres 18.6, mismo servidor).
- Llamada directa a `/status` de API-Football confirmó la nueva key activa, plan Pro intacto (2244/7500 requests usados ese día).
- Efecto colateral esperado y observado: el pipeline `train_logistic.py`, que estaba corriendo en background con la credencial vieja, falló con `password authentication failed for user 'neondb_owner'` en cuanto se rotó — confirma que la rotación fue efectiva (la credencial vieja dejó de servir de inmediato) y no fue un bug.

## Consecuencias

- Positivas: ambas credenciales reales que pudieron haber quedado expuestas a un tercero (OpenAI, vía el ZIP) ya no son válidas. No se detectó actividad sospechosa en ninguna de las dos cuentas antes de la rotación (no se investigó exhaustivamente, pero tampoco había indicios).
- Negativas: el pipeline en curso se perdió y hubo que reiniciarlo desde cero (costo de tiempo, no de datos — nada se corrompió).
- Lección para el flujo de trabajo: **antes de compartir el proyecto completo con una herramienta externa (incluyendo otro asistente de IA), excluir explícitamente `.env`** — no alcanza con que esté en `.gitignore`. Vale también para cualquier zip/backup futuro del proyecto.

## Fuentes

Confirmación directa del usuario sobre el contenido del ZIP compartido; verificación empírica de ambas credenciales rotadas mediante scripts propios del proyecto.
