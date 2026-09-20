"""Fase 5 (continuación, ADR-0010): búsqueda acotada de hiperparámetros de
Elo, con separación estricta train/validation/test para no violar ADR-0007
("no seleccionar el mejor modelo utilizando el mismo dataset final de test"):

  - train:      2022        (para ajustar ratings)
  - validation: 2023        (para ELEGIR k_factor/home_advantage)
  - test:       2024        (held-out real — nunca se toca durante la
                              selección de hiperparámetros; es el único
                              número que se compara contra naive al final)

Si el Elo ajustado no le gana a naive en el fold de test, se reporta así
de honesto — no se sigue buscando hiperparámetros hasta forzar una victoria
en el propio test set, porque eso invalidaría la comparación.
"""

import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
sys.stdout.reconfigure(line_buffering=True)  # progreso visible en tiempo real, no solo al terminar
from app.db import SessionLocal  # noqa: E402
from app.evaluation import compute_all_metrics  # noqa: E402
from app.git_info import get_git_sha, is_git_dirty  # noqa: E402
from app.external.api_football import LIGA_PROFESIONAL_ARGENTINA_ID  # noqa: E402
from app.models import Competition, ModelVersion, Season  # noqa: E402
from app.prediction_models import elo, naive  # noqa: E402
from pipelines.evaluate_baselines import get_season_matches  # noqa: E402

K_FACTOR_GRID = [10.0, 20.0, 30.0, 40.0]
HOME_ADVANTAGE_GRID = [30.0, 60.0, 90.0, 120.0]


def evaluate_on_season(session, predict_fn, params, season) -> dict:
    import numpy as np

    matches = get_season_matches(session, season)
    y_true, y_pred = [], []
    for m in matches:
        y_pred.append(predict_fn(m.home_team_id, m.away_team_id, params))
        y_true.append(0 if m.home_goals > m.away_goals else (2 if m.away_goals > m.home_goals else 1))
    return compute_all_metrics(np.array(y_true), np.array(y_pred))


def main() -> int:
    session = SessionLocal()
    try:
        competition = session.query(Competition).filter_by(api_football_id=LIGA_PROFESIONAL_ARGENTINA_ID).one()
        seasons = {s.year_label: s for s in session.query(Season).filter_by(competition_id=competition.id).all()}
        validation_season, test_season = seasons["2023"], seasons["2024"]

        print("=== Búsqueda de hiperparámetros (train=2022, validation=2023) ===")
        results = []
        for k in K_FACTOR_GRID:
            for home_adv in HOME_ADVANTAGE_GRID:
                params = elo.fit(session, validation_season.start_date, k_factor=k, home_advantage=home_adv)
                metrics = evaluate_on_season(session, elo.predict_proba, params, validation_season)
                results.append((k, home_adv, metrics["log_loss"]))
                print(f"k={k:5.1f}  home_advantage={home_adv:6.1f}  log_loss={metrics['log_loss']:.4f}")

        best_k, best_home_adv, best_val_log_loss = min(results, key=lambda r: r[2])
        print(f"\nMejor combinación en validación: k={best_k}, home_advantage={best_home_adv} (log_loss={best_val_log_loss:.4f})")

        print("\n=== Evaluación final en held-out real (test=2024, nunca usado para elegir hiperparámetros) ===")
        final_params = elo.fit(session, test_season.start_date, k_factor=best_k, home_advantage=best_home_adv)
        test_metrics = evaluate_on_season(session, elo.predict_proba, final_params, test_season)
        print(f"baseline_elo_tuned  n={test_metrics['n_samples']}  log_loss={test_metrics['log_loss']:.4f}  brier={test_metrics['brier_score']:.4f}  acc={test_metrics['accuracy']:.3f}  ece={test_metrics['ece']:.4f}")

        naive_params = naive.fit(session, test_season.start_date)
        naive_metrics = evaluate_on_season(session, lambda h, a, p: naive.predict_proba(p), naive_params, test_season)
        beats_naive = test_metrics["log_loss"] < naive_metrics["log_loss"]
        print(f"\nnaive en el mismo fold de test (2024): log_loss={naive_metrics['log_loss']:.4f}")
        print("RESULTADO: " + ("elo_tuned SUPERA a naive en el held-out real." if beats_naive else "elo_tuned NO supera a naive en el held-out real, incluso tras ajustar hiperparámetros."))

        existing = session.query(ModelVersion).filter_by(name="baseline_elo", version_tag="v2").one_or_none()
        if existing is None:
            parent = session.query(ModelVersion).filter_by(name="baseline_elo", version_tag="v1").one_or_none()
            session.add(
                ModelVersion(
                    name="baseline_elo",
                    version_tag="v2",
                    algorithm_family="elo",
                    training_dataset_version="v1",
                    hyperparameters={**final_params, "tuned_k_factor": best_k, "tuned_home_advantage": best_home_adv, "validation_log_loss": best_val_log_loss},
                    trained_at=datetime.now(timezone.utc),
                    status="candidate",  # sigue como candidato: un solo fold de test no alcanza para "mejora consistente" (ADR-0007)
                    git_sha=get_git_sha(),
                    git_dirty=is_git_dirty(),
                    parent_model_version_id=parent.id if parent else None,
                )
            )
            session.commit()
            print("\nRegistrado como model_versions: baseline_elo v2 (status=candidate, NO promovido — un solo fold no es evidencia suficiente de mejora consistente).")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
