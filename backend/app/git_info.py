"""Trazabilidad barata (ADR-0013/ADR-0014): saber con qué código exacto se
entrenó un modelo, sin necesitar todavía un pipeline de entrenamiento
automatizado ni artifacts serializados."""

import subprocess


def get_git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        )
        return result.stdout.strip()
    except Exception:
        return None


def is_git_dirty() -> bool | None:
    """True si hay cambios sin commitear en el working tree al momento de
    entrenar — git_sha solo no alcanza: un modelo entrenado con features.py
    modificado sin commitear no corresponde realmente a ese SHA (ADR-0014).
    None si no se pudo determinar (no es un repo git, git no disponible)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5, check=True
        )
        return bool(result.stdout.strip())
    except Exception:
        return None
