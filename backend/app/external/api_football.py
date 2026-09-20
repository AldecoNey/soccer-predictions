"""Cliente mínimo para api-sports.io (API-Football v3).

Ver ADR-0003 para la elección de esta fuente y sus restricciones de plan
(el free tier NO cubre la temporada en curso — solo 2022-2024 al 2026-09-19,
verificado empíricamente, no asumido de la documentación de marketing).

LIGA_PROFESIONAL_ARGENTINA_ID = 128 (verificado contra la API real via
GET /leagues?country=Argentina — el valor de 44 que circuló en investigación
previa era incorrecto, correspondía a la FA WSL de Inglaterra).
"""

import requests

from app.config import settings

BASE_URL = "https://v3.football.api-sports.io"
LIGA_PROFESIONAL_ARGENTINA_ID = 128


class ApiFootballError(RuntimeError):
    pass


def _get(path: str, params: dict) -> list[dict]:
    response = requests.get(
        f"{BASE_URL}{path}",
        headers={"x-apisports-key": settings.api_football_key},
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("errors"):
        raise ApiFootballError(str(payload["errors"]))
    return payload["response"]


def get_league_seasons(league_id: int = LIGA_PROFESIONAL_ARGENTINA_ID) -> list[dict]:
    """Devuelve la lista de temporadas disponibles para la liga, con sus
    fechas de inicio/fin y cobertura de datos declarada por el proveedor."""
    response = _get("/leagues", {"id": league_id})
    return response[0]["seasons"] if response else []


def get_fixtures(season: int, league_id: int = LIGA_PROFESIONAL_ARGENTINA_ID) -> list[dict]:
    """Devuelve todos los fixtures (partidos) de una temporada. Lanza
    ApiFootballError si el plan actual no tiene acceso a esa temporada."""
    return _get("/fixtures", {"league": league_id, "season": season})


def get_lineups(fixture_id: int) -> list[dict]:
    """Alineaciones titulares de un partido (1 request por partido — no hay
    forma de traer varios partidos en una sola llamada). Devuelve una lista
    de hasta 2 elementos (uno por equipo), o [] si el proveedor no tiene
    alineación cargada para ese partido (pasa con partidos muy viejos o
    de categorías menores)."""
    return _get("/fixtures/lineups", {"fixture": fixture_id})
