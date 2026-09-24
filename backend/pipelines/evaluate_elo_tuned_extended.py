"""Evaluation & Calibration (independiente de Modeling, ADR-0005): evaluación
extendida de `baseline_elo` v2 (k_factor=10, home_advantage=120, elegidos en
`pipelines/tune_elo.py` con train=2022/validation=2023/test=2024 — ver
ADR-0010) sobre los folds de 2025 y 2026, que no existían cuando se hizo esa
búsqueda de hiperparámetros.

IMPORTANTE — esto NO es una nueva búsqueda de hiperparámetros:

  - k_factor=10 y home_advantage=120 quedan FIJOS. Re-optimizarlos usando
    2025/2026 sería exactamente la violación de ADR-0007 que tune_elo.py
    evitó con cuidado: dejar que un fold influya en el propio parámetro que
    se está evaluando sobre él.
  - 2023 quedó "gastado" como validation set en tune_elo.py (sirvió para
    ELEGIR k_factor/home_advantage) y 2024 ya fue reportado en ADR-0010 como
    el único fold de test real hasta ahora. Ninguno de los dos es evidencia
    nueva e independiente — se re-corren acá solo como chequeo de que este
    script reproduce exactamente los números ya publicados, no como fold
    adicional en el veredicto final.
  - Los folds nuevos e independientes son eval=2025 y eval=2026 (temporada en
    curso al momento de esta corrida, 2026-09-24 — evaluada solo sobre los
    partidos ya finalizados).

Estructura de folds: misma ventana expansiva de `evaluate_baselines.get_folds`
usada en ADR-0011/ADR-0022 (train=2022 -> eval 2023; train=2022-23 -> eval
2024; train=2022-24 -> eval 2025; train=2022-25 -> eval 2026).

Este script NO cambia `model_versions.status` de ningún modelo (ADR-0014):
solo registra evidencia en `evaluation_metrics`, más una fila nueva en
`model_versions` (name="baseline_elo", version_tag="v2-extended-eval",
status="candidate") para poder asociarle las métricas de esta corrida sin
tocar ni duplicar la fila v2 original de tune_elo.py. La recomendación
PROMOTE/REJECT/INCONCLUSIVE se entrega en el reporte de este agente al
Orquestador, no se ejecuta acá.
"""

import sys
from datetime import datetime, timezone

import numpy as np

sys.path.insert(0, ".")
sys.stdout.reconfigure(line_buffering=True)  # progreso visible en tiempo real, no solo al terminar
from app.db import SessionLocal  # noqa: E402
from app.evaluation import compute_all_metrics  # noqa: E402
from app.git_info import get_git_sha, is_git_dirty  # noqa: E402
from app.external.api_football import LIGA_PROFESIONAL_ARGENTINA_ID  # noqa: E402
from app.models import Competition, EvaluationMetric, ModelVersion  # noqa: E402
from app.prediction_models import elo, naive  # noqa: E402
from pipelines.evaluate_baselines import get_folds, get_season_matches  # noqa: E402

# Fijos (ADR-0010 / tune_elo.py) — NO re-optimizar acá.
FIXED_K_FACTOR = 10.0
FIXED_HOME_ADVANTAGE = 120.0

# Folds que son evidencia nueva e independiente para esta evaluación.
# 2023/2024 se corren solo como chequeo de reproducibilidad (ver docstring).
NEW_EVIDENCE_EVAL_YEARS = {"2025", "2026"}
SANITY_CHECK_EVAL_YEARS = {"2023", "2024"}


def evaluate_fold(session, predict_fn, params, eval_season) -> tuple[dict, np.ndarray, np.ndarray]:
    matches = get_season_matches(session, eval_season)
    y_true, y_pred = [], []
    for m in matches:
        y_pred.append(predict_fn(m.home_team_id, m.away_team_id, params))
        y_true.append(0 if m.home_goals > m.away_goals else (2 if m.away_goals > m.home_goals else 1))
    y_true_arr, y_pred_arr = np.array(y_true), np.array(y_pred)
    return compute_all_metrics(y_true_arr, y_pred_arr), y_true_arr, y_pred_arr


def main() -> int:
    session = SessionLocal()
    try:
        competition = session.query(Competition).filter_by(api_football_id=LIGA_PROFESIONAL_ARGENTINA_ID).one()
        folds = get_folds(session, competition.id)
        evaluation_run_at = datetime.now(timezone.utc)

        elo_version = session.query(ModelVersion).filter_by(name="baseline_elo", version_tag="v2-extended-eval").one_or_none()
        if elo_version is None:
            parent = session.query(ModelVersion).filter_by(name="baseline_elo", version_tag="v2").one_or_none()
            elo_version = ModelVersion(
                name="baseline_elo",
                version_tag="v2-extended-eval",
                algorithm_family="elo",
                training_dataset_version="v1",
                hyperparameters={
                    "k_factor": FIXED_K_FACTOR,
                    "home_advantage": FIXED_HOME_ADVANTAGE,
                    "note": (
                        "Hiperparametros FIJOS, heredados de tune_elo.py / ADR-0010 "
                        "(train=2022, validation=2023). NO re-tuneados con 2025/2026. "
                        "Esta version extiende la evaluacion de baseline_elo v2 a los "
                        "folds eval=2025 y eval=2026, evidencia nueva e independiente "
                        "que no existia al momento de tune_elo.py."
                    ),
                },
                trained_at=datetime.now(timezone.utc),
                status="candidate",  # el Orquestador decide si esto cambia, no este script (ADR-0014)
                git_sha=get_git_sha(),
                git_dirty=is_git_dirty(),
                parent_model_version_id=parent.id if parent else None,
            )
            session.add(elo_version)
            session.flush()

        naive_version = session.query(ModelVersion).filter_by(name="baseline_naive", version_tag="v1").one_or_none()
        if naive_version is None:
            raise RuntimeError("baseline_naive v1 no encontrado en model_versions — se esperaba que ya existiera de evaluate_baselines.py")

        summary_rows = []  # (eval_year, is_new_evidence, elo_metrics, naive_metrics, elo_beats_naive)
        elo_all_true, elo_all_pred = [], []
        naive_all_true, naive_all_pred = [], []

        for fold in folds:
            eval_season = fold["eval_season"]
            eval_year = eval_season.year_label
            if eval_year not in NEW_EVIDENCE_EVAL_YEARS and eval_year not in SANITY_CHECK_EVAL_YEARS:
                continue

            is_new_evidence = eval_year in NEW_EVIDENCE_EVAL_YEARS
            tag = "NUEVA EVIDENCIA" if is_new_evidence else "chequeo de reproducibilidad (ya reportado)"
            print(f"\n=== Fold: train={fold['train_years']} -> eval={eval_year} ({tag}) ===")

            as_of = eval_season.start_date
            elo_params = elo.fit(session, as_of, k_factor=FIXED_K_FACTOR, home_advantage=FIXED_HOME_ADVANTAGE)
            elo_metrics, elo_y_true, elo_y_pred = evaluate_fold(session, elo.predict_proba, elo_params, eval_season)

            naive_params = naive.fit(session, as_of)
            naive_metrics, naive_y_true, naive_y_pred = evaluate_fold(
                session, lambda h, a, p: naive.predict_proba(p), naive_params, eval_season
            )

            beats_naive = elo_metrics["log_loss"] < naive_metrics["log_loss"]
            print(
                f"elo_tuned(k={FIXED_K_FACTOR},home_adv={FIXED_HOME_ADVANTAGE})  "
                f"n={elo_metrics['n_samples']:4d}  log_loss={elo_metrics['log_loss']:.4f}  "
                f"brier={elo_metrics['brier_score']:.4f}  acc={elo_metrics['accuracy']:.3f}  ece={elo_metrics['ece']:.4f}"
            )
            print(
                f"naive                                   n={naive_metrics['n_samples']:4d}  "
                f"log_loss={naive_metrics['log_loss']:.4f}  brier={naive_metrics['brier_score']:.4f}  "
                f"acc={naive_metrics['accuracy']:.3f}  ece={naive_metrics['ece']:.4f}"
            )
            print(f"-> elo_tuned {'SUPERA' if beats_naive else 'NO supera'} a naive en log_loss en este fold.")

            summary_rows.append((eval_year, is_new_evidence, elo_metrics, naive_metrics, beats_naive))

            session.add(
                EvaluationMetric(
                    model_version_id=elo_version.id,
                    evaluation_run_at=evaluation_run_at,
                    segment=f"fold={eval_year}",
                    log_loss=elo_metrics["log_loss"],
                    brier_score=elo_metrics["brier_score"],
                    ece=elo_metrics["ece"],
                    accuracy=elo_metrics["accuracy"],
                    n_samples=elo_metrics["n_samples"],
                )
            )
            session.add(
                EvaluationMetric(
                    model_version_id=naive_version.id,
                    evaluation_run_at=evaluation_run_at,
                    segment=f"fold={eval_year}(extended-eval-comparison)",
                    log_loss=naive_metrics["log_loss"],
                    brier_score=naive_metrics["brier_score"],
                    ece=naive_metrics["ece"],
                    accuracy=naive_metrics["accuracy"],
                    n_samples=naive_metrics["n_samples"],
                )
            )

            if is_new_evidence:
                elo_all_true.append(elo_y_true)
                elo_all_pred.append(elo_y_pred)
                naive_all_true.append(naive_y_true)
                naive_all_pred.append(naive_y_pred)

        # Agregado SOLO de la evidencia nueva (2025+2026) -- 2023/2024 no se
        # mezclan aca, ya estan gastados/reportados y mezclarlos infla
        # artificialmente la evidencia "independiente" (ver docstring).
        if elo_all_true:
            agg_elo_true = np.concatenate(elo_all_true)
            agg_elo_pred = np.concatenate(elo_all_pred)
            agg_naive_true = np.concatenate(naive_all_true)
            agg_naive_pred = np.concatenate(naive_all_pred)
            agg_elo_metrics = compute_all_metrics(agg_elo_true, agg_elo_pred)
            agg_naive_metrics = compute_all_metrics(agg_naive_true, agg_naive_pred)

            print("\n=== Agregado SOLO evidencia nueva (eval=2025 + eval=2026) ===")
            print(
                f"elo_tuned  n={agg_elo_metrics['n_samples']:4d}  log_loss={agg_elo_metrics['log_loss']:.4f}  "
                f"brier={agg_elo_metrics['brier_score']:.4f}  acc={agg_elo_metrics['accuracy']:.3f}  ece={agg_elo_metrics['ece']:.4f}"
            )
            print(
                f"naive      n={agg_naive_metrics['n_samples']:4d}  log_loss={agg_naive_metrics['log_loss']:.4f}  "
                f"brier={agg_naive_metrics['brier_score']:.4f}  acc={agg_naive_metrics['accuracy']:.3f}  ece={agg_naive_metrics['ece']:.4f}"
            )

            session.add(
                EvaluationMetric(
                    model_version_id=elo_version.id,
                    evaluation_run_at=evaluation_run_at,
                    segment="overall_new_evidence_2025_2026",
                    log_loss=agg_elo_metrics["log_loss"],
                    brier_score=agg_elo_metrics["brier_score"],
                    ece=agg_elo_metrics["ece"],
                    accuracy=agg_elo_metrics["accuracy"],
                    n_samples=agg_elo_metrics["n_samples"],
                )
            )
            session.add(
                EvaluationMetric(
                    model_version_id=naive_version.id,
                    evaluation_run_at=evaluation_run_at,
                    segment="overall_new_evidence_2025_2026(extended-eval-comparison)",
                    log_loss=agg_naive_metrics["log_loss"],
                    brier_score=agg_naive_metrics["brier_score"],
                    ece=agg_naive_metrics["ece"],
                    accuracy=agg_naive_metrics["accuracy"],
                    n_samples=agg_naive_metrics["n_samples"],
                )
            )

        print("\n=== Resumen por fold ===")
        print(f"{'eval':6s} {'tipo':28s} {'elo_logloss':>12s} {'naive_logloss':>14s} {'elo<naive?':>11s}")
        for eval_year, is_new_evidence, elo_metrics, naive_metrics, beats_naive in summary_rows:
            tipo = "nueva evidencia" if is_new_evidence else "sanity check (gastado)"
            print(
                f"{eval_year:6s} {tipo:28s} {elo_metrics['log_loss']:12.4f} "
                f"{naive_metrics['log_loss']:14.4f} {str(beats_naive):>11s}"
            )

        new_evidence_rows = [r for r in summary_rows if r[1]]
        all_new_beat_naive = all(r[4] for r in new_evidence_rows) if new_evidence_rows else None
        print("\n=== Veredicto de consistencia (solo evidencia nueva: 2025, 2026) ===")
        if all_new_beat_naive is None:
            print("Sin folds nuevos evaluados -- no se puede concluir nada.")
        elif all_new_beat_naive:
            print("elo_tuned supera a naive en TODOS los folds nuevos e independientes.")
        else:
            print("elo_tuned NO supera a naive de forma consistente en los folds nuevos -- revisar resumen por fold arriba.")

        session.commit()
        print(f"\nOK: métricas persistidas en evaluation_metrics (model_version_id={elo_version.id}, version_tag=v2-extended-eval).")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
