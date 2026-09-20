"""Trazabilidad barata (ADR-0013): saber con qué código exacto se entrenó
un modelo, sin necesitar todavía un pipeline de entrenamiento automatizado
ni artifacts serializados."""

import subprocess


def get_git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        )
        return result.stdout.strip()
    except Exception:
        return None
