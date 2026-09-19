"""Fase 5 (ROADMAP): walk-forward validation de los 3 baselines de Fase 4.

Folds por temporada (expanding window, ADR-0007 — nunca random split):
  Fold 1: entrenar con 2022            -> evaluar 2023
  Fold 2: entrenar con 2022+2023       -> evaluar 2024

Cada baseline se re-entrena con solo los datos anteriores al inicio de la
temporada de evaluación (via as_of=season.start_date, que ya respeta
RESULT_KNOWN_BUFFER a través de get_historical_matches). Ninguna fila de la
temporada evaluada participa en su propio entrenamiento.

Nota (ver app/models.py::EvaluationMetric): el desglose "por horizonte"
T-72/T-24/T-2 no aplica todavía porque ninguno de estos 3 baselines
consume features sensibles a la cercanía del kickoff — eso empieza en
Fase 6. Se evalúa "overall" y por local/visitante.
"""

import sys
import uuid
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select

sys.path.insert(0, ".")
from app.db import SessionLocal  # noqa: E402
from app.evaluation import compute_all_metrics  # noqa: E402
from app.external.api_football import LIGA_PROFESIONAL_ARGENTINA_ID  # noqa: E402
from app.models import Competition, EvaluationMetric, Match, ModelVersion, Result, Season  # noqa: E402
from app.prediction_models import elo, naive, poisson_dixon_coles  # noqa: E402
from app.prediction_models.data import HistoricalMatch  # noqa: E402

OUTCOME_INDEX = {"home": 0, "draw": 1, "away": 2}

BASELINES = {
    "baseline_naive": {
        "fit": lambda session, as_of: naive.fit(session, as_of),
        "predict": lambda home_id, away_id, params: naive.predict_proba(params),
    },
    "baseline_elo": {
        "fit": lambda session, as_of: elo.fit(session, as_of),
        "predict": elo.predict_proba,
    },
    "baseline_poisson_dixon_coles": {
        "fit": lambda session, as_of: poisson_dixon_coles.fit(session, as_of),
        "predict": poisson_dixon_coles.predict_proba,
    },
}


def get_folds(session, competition_id: uuid.UUID) -> list[dict]:
    """Ojo: debe filtrar por competición — sin esto, mezcla temporadas de
    distintas ligas que casualmente comparten year_label (bug real detectado
    por test_get_folds_builds_expanding_windows contaminándose con datos de
    otra competición en la misma base)."""
    seasons = {s.year_label: s for s in session.query(Season).filter_by(competition_id=competition_id).all()}
    ordered_years = sorted(seasons.keys())
    folds = []
    for i in range(1, len(ordered_years)):
        eval_year = ordered_years[i]
        train_years = ordered_years[:i]
        folds.append({"train_years": train_years, "eval_season": seasons[eval_year]})
    return folds


def get_season_matches(session, season: Season) -> list[HistoricalMatch]:
    """Todos los partidos finalizados de una temporada (para evaluarlos), sin
    el corte anti-leakage de get_historical_matches — ese corte es para
    decidir qué usar como INPUT de entrenamiento, no para listar qué existe."""
    stmt = (
        select(Match, Result)
        .join(Result, Result.match_id == Match.id)
        .where(Match.season_id == season.id, Match.status == "finished")
        .order_by(Match.kickoff_at.asc())
    )
    rows = session.execute(stmt).all()
    return [
        HistoricalMatch(
            home_team_id=match.home_team_id,
            away_team_id=match.away_team_id,
            home_team_name="",
            away_team_name="",
            kickoff_at=match.kickoff_at,
            home_goals=result.home_score,
            away_goals=result.away_score,
        )
        for match, result in rows
    ]


def run_fold(session, model_name: str, model_fns: dict, eval_season: Season) -> tuple[np.ndarray, np.ndarray, list]:
    """Devuelve (y_true, y_pred, partidos evaluados) para el fold."""
    as_of = eval_season.start_date
    params = model_fns["fit"](session, as_of)

    eval_matches = get_season_matches(session, eval_season)

    y_true, y_pred = [], []
    for m in eval_matches:
        p_home, p_draw, p_away = model_fns["predict"](m.home_team_id, m.away_team_id, params)
        y_pred.append([p_home, p_draw, p_away])
        outcome = "home" if m.home_goals > m.away_goals else ("away" if m.away_goals > m.home_goals else "draw")
        y_true.append(OUTCOME_INDEX[outcome])

    return np.array(y_true), np.array(y_pred), eval_matches


def main() -> int:
    session = SessionLocal()
    try:
        competition = session.query(Competition).filter_by(api_football_id=LIGA_PROFESIONAL_ARGENTINA_ID).one()
        folds = get_folds(session, competition.id)
        evaluation_run_at = datetime.now(timezone.utc)
        report: dict[str, list] = {name: [] for name in BASELINES}

        for fold_idx, fold in enumerate(folds, start=1):
            eval_season = fold["eval_season"]
            print(f"\n=== Fold {fold_idx}: train={fold['train_years']} -> eval={eval_season.year_label} ===")

            for model_name, model_fns in BASELINES.items():
                y_true, y_pred, matches = run_fold(session, model_name, model_fns, eval_season)
                metrics = compute_all_metrics(y_true, y_pred)
                print(f"{model_name:30s} n={metrics['n_samples']:4d}  log_loss={metrics['log_loss']:.4f}  brier={metrics['brier_score']:.4f}  acc={metrics['accuracy']:.3f}  ece={metrics['ece']:.4f}")
                report[model_name].append((f"fold={eval_season.year_label}", metrics, y_true, y_pred))

        print("\n=== Métricas agregadas (todas las temporadas evaluadas juntas) ===")
        model_version_by_name = {mv.name: mv for mv in session.query(ModelVersion).filter_by(version_tag="v1").all()}

        for model_name, fold_results in report.items():
            all_true = np.concatenate([r[2] for r in fold_results])
            all_pred = np.concatenate([r[3] for r in fold_results])
            overall = compute_all_metrics(all_true, all_pred)
            print(f"{model_name:30s} n={overall['n_samples']:4d}  log_loss={overall['log_loss']:.4f}  brier={overall['brier_score']:.4f}  acc={overall['accuracy']:.3f}  ece={overall['ece']:.4f}")

            model_version = model_version_by_name[model_name]
            segments = [("overall", all_true, all_pred)]
            for fold_label, _, y_true, y_pred in fold_results:
                segments.append((fold_label, y_true, y_pred))

            for segment_label, y_true, y_pred in segments:
                m = compute_all_metrics(y_true, y_pred)
                session.add(
                    EvaluationMetric(
                        model_version_id=model_version.id,
                        evaluation_run_at=evaluation_run_at,
                        segment=segment_label,
                        log_loss=m["log_loss"],
                        brier_score=m["brier_score"],
                        ece=m["ece"],
                        accuracy=m["accuracy"],
                        n_samples=m["n_samples"],
                    )
                )
        session.commit()
        print("\nOK: métricas persistidas en evaluation_metrics.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
