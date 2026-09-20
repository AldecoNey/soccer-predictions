"""Fase 6: ¿rotation_index tiene algo de poder predictivo en absoluto?

Este NO es un backtest comparable a los de ADR-0010 (naive/elo/poisson-dc).
Es un experimento oracle/diagnóstico: rotation_index usa la alineación REAL
del propio partido (ver app/features_lineup.py), algo que en T-72/T-24 no
existe todavía y en T-2 tampoco existe tal cual sin más trabajo (ver nota
abajo). Sirve únicamente para responder "¿esta clase de señal aporta algo,
en principio?" — su resultado nunca se reporta como si fuera el de un
modelo desplegable, y walk-forward por temporada aquí es solo para no
comparar peras con manzanas entre variantes, no una certificación de que
esto sea seguro para producción.

Camino a una versión realmente desplegable (Fase 7, no acá): requeriría un
`observed_at` real de cuándo el sistema efectivamente vio la alineación
confirmada de cada partido — no una constante de minutos-antes-del-kickoff
asumida (varía por liga/proveedor y se mide, no se supone).
"""

import sys
from datetime import datetime, timedelta, timezone

import numpy as np

sys.path.insert(0, ".")
sys.stdout.reconfigure(line_buffering=True)  # progreso visible en tiempo real, no solo al terminar
from app.db import SessionLocal, with_retries  # noqa: E402
from app.evaluation import compute_all_metrics  # noqa: E402
from app.external.api_football import LIGA_PROFESIONAL_ARGENTINA_ID  # noqa: E402
from app.features import build_features  # noqa: E402
from app.git_info import get_git_sha, is_git_dirty  # noqa: E402
from app.features_lineup import rotation_index  # noqa: E402
from app.models import Competition, ModelVersion, Season  # noqa: E402
from app.prediction_models import logistic  # noqa: E402
from pipelines.evaluate_baselines import get_folds, get_season_matches  # noqa: E402

NEAR_KICKOFF_OFFSET = timedelta(hours=2)  # simula un snapshot "T-2" (alineación ya confirmada)


COMMIT_EVERY = 100  # corta la transacción periódicamente: una sesión con una
# transacción de lectura abierta por miles de queries corridas puede sobrevivir
# a la conexión real (Neon la cierra) sin que pool_pre_ping lo note, porque
# pre_ping solo valida conexiones AL SACARLAS del pool, no una ya en uso.


def _extract_one(session, m, with_rotation: bool):
    as_of = m.kickoff_at - NEAR_KICKOFF_OFFSET
    features = build_features(session, m.id, as_of)
    rotation = None
    if with_rotation:
        rotation = {
            "home": rotation_index(session, m.id, m.home_team_id),
            "away": rotation_index(session, m.id, m.away_team_id),
        }
    return features, rotation


def build_dataset(session, matches, with_rotation: bool):
    x, y = [], []
    for i, m in enumerate(matches, start=1):
        try:
            features, rotation = with_retries(session, lambda m=m: _extract_one(session, m, with_rotation))
        except ValueError:
            continue
        x.append(logistic.vectorize(features, rotation))
        outcome = 0 if m.home_goals > m.away_goals else (2 if m.away_goals > m.home_goals else 1)
        y.append(outcome)
        if i % COMMIT_EVERY == 0:
            session.commit()  # no-op sobre datos (solo lecturas) — cierra la transacción actual
    session.commit()
    return np.array(x), np.array(y)


def main() -> int:
    session = SessionLocal()
    try:
        competition = session.query(Competition).filter_by(api_football_id=LIGA_PROFESIONAL_ARGENTINA_ID).one()
        folds = get_folds(session, competition.id)
        evaluation_run_at = datetime.now(timezone.utc)

        variants = {"logistic_no_rotation": False, "logistic_with_rotation": True}
        all_results: dict[str, list] = {name: [] for name in variants}

        for fold_idx, fold in enumerate(folds, start=1):
            eval_season = fold["eval_season"]
            train_seasons = (
                session.query(Season)
                .filter(Season.competition_id == competition.id, Season.year_label.in_(fold["train_years"]))
                .all()
            )
            train_matches = []
            for s in train_seasons:
                train_matches.extend(get_season_matches(session, s))
            eval_matches = get_season_matches(session, eval_season)

            print(f"\n=== Fold {fold_idx}: train={fold['train_years']} ({len(train_matches)} partidos) -> eval={eval_season.year_label} ({len(eval_matches)} partidos) ===")

            for name, with_rotation in variants.items():
                x_train, y_train = build_dataset(session, train_matches, with_rotation)
                x_eval, y_eval = build_dataset(session, eval_matches, with_rotation)
                if len(x_train) < 20 or len(x_eval) < 20:
                    print(f"{name}: datos insuficientes en este fold, se omite")
                    continue
                model = logistic.fit(x_train, y_train)
                y_pred = np.array([logistic.predict_proba(model, row) for row in x_eval])
                metrics = compute_all_metrics(y_eval, y_pred)
                print(f"{name:24s} n={metrics['n_samples']:4d}  log_loss={metrics['log_loss']:.4f}  brier={metrics['brier_score']:.4f}  acc={metrics['accuracy']:.3f}")
                all_results[name].append((eval_season.year_label, metrics, y_eval, y_pred))

        print("\n=== Comparación agregada (todas las temporadas evaluadas) ===")
        model_versions_created = []
        for name, fold_results in all_results.items():
            if not fold_results:
                continue
            all_true = np.concatenate([r[2] for r in fold_results])
            all_pred = np.concatenate([r[3] for r in fold_results])
            overall = compute_all_metrics(all_true, all_pred)
            print(f"{name:24s} n={overall['n_samples']:4d}  log_loss={overall['log_loss']:.4f}  brier={overall['brier_score']:.4f}  acc={overall['accuracy']:.3f}")
            model_versions_created.append((name, overall))

        for name, overall in model_versions_created:
            existing = session.query(ModelVersion).filter_by(name=name, version_tag="v1").one_or_none()
            if existing is None:
                session.add(
                    ModelVersion(
                        name=name,
                        version_tag="v1",
                        algorithm_family="logistic",
                        training_dataset_version="v2",  # incluye 2025/2026 (ver ADR-0003 update)
                        hyperparameters={"features": logistic.FEATURE_NAMES_WITH_ROTATION if "rotation" in name else logistic.FEATURE_NAMES},
                        trained_at=evaluation_run_at,
                        status="candidate",
                        git_sha=get_git_sha(),
                        git_dirty=is_git_dirty(),
                    )
                )
        session.commit()
        print("\nOK: registrado en model_versions (candidate).")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
