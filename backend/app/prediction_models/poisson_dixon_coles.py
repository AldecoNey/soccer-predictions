"""Baseline 2 (ADR-0006): Poisson con ajuste Dixon-Coles (Dixon & Coles, 1997)
para la sobre-representación de marcadores bajos (0-0, 1-0, 0-1, 1-1).

λ_local = exp(ataque_local - defensa_visitante + ventaja_local)
λ_visitante = exp(ataque_visitante - defensa_local)
P(x,y) = τ(x,y; λ_local, λ_visitante, ρ) · Poisson(x; λ_local) · Poisson(y; λ_visitante)

Se ajusta por máxima verosimilitud (L-BFGS-B, determinista — no requiere
seed para ser reproducible). Se agrega una regularización L2 pequeña sobre
ataque/defensa solo para estabilidad numérica: el modelo es invariante ante
un corrimiento global (ataque_i += c, defensa_i += c no cambia ninguna
predicción), y sin ella el optimizador puede derivar sin converger por esa
dirección plana.
"""

import uuid
from datetime import datetime

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson as poisson_dist
from sqlalchemy.orm import Session

from app.prediction_models.contract import validate_probability_triple
from app.prediction_models.data import get_historical_matches

L2_REGULARIZATION = 0.01
DEFAULT_MAX_GOALS = 8


def _tau(x: int, y: int, lambda_x: float, lambda_y: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - lambda_x * lambda_y * rho
    if x == 0 and y == 1:
        return 1 + lambda_x * rho
    if x == 1 and y == 0:
        return 1 + lambda_y * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def fit(session: Session, as_of_timestamp: datetime, max_goals: int = DEFAULT_MAX_GOALS) -> dict:
    matches = get_historical_matches(session, as_of_timestamp)
    team_ids = sorted({str(m.home_team_id) for m in matches} | {str(m.away_team_id) for m in matches})
    n = len(team_ids)
    idx = {t: i for i, t in enumerate(team_ids)}

    if n == 0 or not matches:
        return {"team_ids": [], "attack": [], "defense": [], "home_advantage": 0.0, "rho": 0.0, "n_matches": 0, "converged": False}

    home_idx = np.array([idx[str(m.home_team_id)] for m in matches])
    away_idx = np.array([idx[str(m.away_team_id)] for m in matches])
    home_goals = np.array([m.home_goals for m in matches])
    away_goals = np.array([m.away_goals for m in matches])

    def unpack(params: np.ndarray):
        attack = params[:n]
        defense = params[n : 2 * n]
        home_adv = params[2 * n]
        rho = params[2 * n + 1]
        return attack, defense, home_adv, rho

    def neg_log_likelihood(params: np.ndarray) -> float:
        attack, defense, home_adv, rho = unpack(params)
        lam_h = np.exp(attack[home_idx] - defense[away_idx] + home_adv)
        lam_a = np.exp(attack[away_idx] - defense[home_idx])

        log_lik = 0.0
        for i in range(len(matches)):
            tau = _tau(int(home_goals[i]), int(away_goals[i]), lam_h[i], lam_a[i], rho)
            p = max(tau, 1e-10) * poisson_dist.pmf(home_goals[i], lam_h[i]) * poisson_dist.pmf(away_goals[i], lam_a[i])
            log_lik += np.log(max(p, 1e-10))

        regularization = L2_REGULARIZATION * (np.sum(attack**2) + np.sum(defense**2))
        return -log_lik + regularization

    initial_params = np.zeros(2 * n + 2)
    initial_params[2 * n] = 0.2  # prior razonable de ventaja local
    result = minimize(
        neg_log_likelihood,
        initial_params,
        method="L-BFGS-B",
        bounds=[(-3, 3)] * n + [(-3, 3)] * n + [(-1, 1)] + [(-0.3, 0.3)],
    )
    attack, defense, home_adv, rho = unpack(result.x)

    return {
        "team_ids": team_ids,
        "attack": attack.tolist(),
        "defense": defense.tolist(),
        "home_advantage": float(home_adv),
        "rho": float(rho),
        "n_matches": len(matches),
        "converged": bool(result.success),
    }


def predict_proba(
    home_team_id: uuid.UUID, away_team_id: uuid.UUID, params: dict, max_goals: int = DEFAULT_MAX_GOALS
) -> tuple[float, float, float]:
    team_ids = params["team_ids"]
    if str(home_team_id) not in team_ids or str(away_team_id) not in team_ids:
        # equipo sin historial suficiente al momento de as_of: sin señal, no adivinar
        return 1 / 3, 1 / 3, 1 / 3

    hi, ai = team_ids.index(str(home_team_id)), team_ids.index(str(away_team_id))
    attack, defense = params["attack"], params["defense"]
    lam_h = np.exp(attack[hi] - defense[ai] + params["home_advantage"])
    lam_a = np.exp(attack[ai] - defense[hi])
    rho = params["rho"]

    grid = np.zeros((max_goals + 1, max_goals + 1))
    for x in range(max_goals + 1):
        for y in range(max_goals + 1):
            grid[x, y] = _tau(x, y, lam_h, lam_a, rho) * poisson_dist.pmf(x, lam_h) * poisson_dist.pmf(y, lam_a)

    # tau(x,y) puede volverse negativo para combinaciones extremas de
    # lambda/rho (ver docstring de _tau) — una celda "negativa" de la grilla
    # no es una probabilidad válida. Clampear a 0 antes de sumar/normalizar es
    # la mitigación estándar en implementaciones de Dixon-Coles (no oculta el
    # problema: si esto pasa seguido para un equipo/temporada, es señal de que
    # los bounds de rho/lambda necesitan revisión, no algo a ignorar).
    grid = np.clip(grid, 0.0, None)
    grid_sum = grid.sum()
    if grid_sum <= 0:
        raise ValueError(f"Grilla Dixon-Coles degenerada (suma={grid_sum}) para home={home_team_id} away={away_team_id}")
    grid = grid / grid_sum
    p_home = float(np.tril(grid, k=-1).sum())
    p_draw = float(np.trace(grid))
    p_away = float(np.triu(grid, k=1).sum())
    return validate_probability_triple(p_home, p_draw, p_away)
