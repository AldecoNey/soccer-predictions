"""Fase 4 (ROADMAP): entrena los 3 baselines de ADR-0006 sobre todo el
histórico disponible y los registra en model_versions como candidatos.

Ninguno se marca status='production' acá — esa decisión es exclusiva de
Evaluation & Calibration Agent (Fase 5, ADR-0005), nunca de quien entrena.
"""

import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
sys.stdout.reconfigure(line_buffering=True)  # progreso visible en tiempo real, no solo al terminar
from app.db import SessionLocal  # noqa: E402
from app.models import ModelVersion  # noqa: E402
from app.prediction_models import elo, naive, poisson_dixon_coles  # noqa: E402
from app.prediction_models.data import get_historical_matches  # noqa: E402

TRAINING_DATASET_VERSION = "v1"  # temporadas 2022-2024 de Liga Profesional Argentina (Fase 2)


def _validate_predictions(name: str, predict_fn, matches, params) -> None:
    """Model tests inline (Sección 22 del brief): 0<=p<=1, suma=1."""
    sample = matches[:20] + matches[-20:]
    for m in sample:
        p_home, p_draw, p_away = predict_fn(m.home_team_id, m.away_team_id, params)
        probs = (p_home, p_draw, p_away)
        assert all(0.0 <= p <= 1.0 for p in probs), f"{name}: probabilidad fuera de [0,1]: {probs}"
        assert abs(sum(probs) - 1.0) < 1e-6, f"{name}: no suma 1: {probs} (suma={sum(probs)})"


def main() -> int:
    session = SessionLocal()
    try:
        as_of = datetime.now(timezone.utc)
        matches = get_historical_matches(session, as_of)
        print(f"Entrenando sobre {len(matches)} partidos históricos (as_of={as_of.isoformat()})")

        # --- Baseline 0: naive ---
        naive_params = naive.fit(session, as_of)
        _validate_predictions("naive", lambda h, a, p: naive.predict_proba(p), matches, naive_params)
        print("naive:", naive_params)

        # --- Baseline 1: elo ---
        elo_params = elo.fit(session, as_of)
        _validate_predictions("elo", elo.predict_proba, matches, elo_params)
        print(f"elo: home_advantage={elo_params['home_advantage']} draw_rate={elo_params['draw_rate']:.3f} n_teams={len(elo_params['ratings'])}")

        # --- Baseline 2: poisson_dixon_coles ---
        pdc_params = poisson_dixon_coles.fit(session, as_of)
        _validate_predictions("poisson_dixon_coles", poisson_dixon_coles.predict_proba, matches, pdc_params)
        print(f"poisson_dixon_coles: home_advantage={pdc_params['home_advantage']:.3f} rho={pdc_params['rho']:.3f} converged={pdc_params['converged']}")

        for name, family, hyperparameters in [
            ("baseline_naive", "naive", naive_params),
            ("baseline_elo", "elo", elo_params),
            ("baseline_poisson_dixon_coles", "poisson_dixon_coles", pdc_params),
        ]:
            existing = session.query(ModelVersion).filter_by(name=name, version_tag="v1").one_or_none()
            if existing is not None:
                print(f"{name} v1 ya existe (id={existing.id}), no se duplica")
                continue
            session.add(
                ModelVersion(
                    name=name,
                    version_tag="v1",
                    algorithm_family=family,
                    training_dataset_version=TRAINING_DATASET_VERSION,
                    hyperparameters=hyperparameters,
                    trained_at=as_of,
                    status="candidate",
                )
            )
        session.commit()
        print("OK: 3 baselines entrenados y registrados como candidatos en model_versions.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
