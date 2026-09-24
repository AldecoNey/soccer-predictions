"""ADR-0022: ¿head_to_head_features aporta señal real, como candidato
deployable (no diagnóstico)?

A diferencia de train_logistic.py (rotation_index, ADR-0011), esta SÍ es una
evaluación comparable a las de ADR-0010: head_to_head_features solo usa
partidos entre los dos equipos ya finalizados antes de `as_of_timestamp`
(mismo corte RESULT_KNOWN_BUFFER que el resto de app/features.py), algo
legítimamente disponible antes del kickoff del partido evaluado — no hay
ventaja de oráculo acá.

Walk-forward por temporada, mismos 4 folds que ADR-0011 (reutiliza
get_folds/get_season_matches de pipelines.evaluate_baselines). No modifica
train_logistic.py ni el experimento de rotation_index, que queda intacto.
"""

import os
import pickle
import sys
from datetime import datetime, timedelta, timezone

import numpy as np

sys.path.insert(0, ".")
sys.stdout.reconfigure(line_buffering=True)  # progreso visible en tiempo real, no solo al terminar
from app.db import SessionLocal, with_retries  # noqa: E402
from app.evaluation import compute_all_metrics  # noqa: E402
from app.external.api_football import LIGA_PROFESIONAL_ARGENTINA_ID  # noqa: E402
from app.features import build_features  # noqa: E402
from app.features_h2h import head_to_head_features  # noqa: E402
from app.git_info import get_git_sha, is_git_dirty  # noqa: E402
from app.models import Competition, ModelVersion, Season  # noqa: E402
from app.prediction_models import logistic  # noqa: E402
from pipelines.evaluate_baselines import get_folds, get_season_matches  # noqa: E402

# T-2 (mismo horizonte que train_logistic.py), aunque a diferencia de
# rotation_index acá no es estrictamente necesario acotarse a T-2:
# head_to_head_features solo depende de partidos YA terminados entre los dos
# equipos, así que el resultado no cambiaría con T-72/T-24. Se usa el mismo
# offset igual para que ambos experimentos sean comparables entre sí y para
# que `as_of` sea siempre estrictamente anterior al kickoff (una predicción
# real nunca se genera exactamente al pitazo inicial).
NEAR_KICKOFF_OFFSET = timedelta(hours=2)

COMMIT_EVERY = 100  # ver train_logistic.py: corta la transacción periódicamente
# para que una sesión de lectura larga no sobreviva a una conexión muerta que
# pool_pre_ping no detecta (pre_ping solo valida al SACAR del pool).

# Desviación deliberada respecto a train_logistic.py (documentada, no un
# cambio silencioso): en esta sesión la conexión a Neon se colgó varias veces
# a mitad de corrida (mismo síntoma ya descrito en app/db.py — CPU en 0, sin
# excepción, el socket nunca vuelve de un read()), y este script no tiene
# checkpointing entre folds. Como `as_of` de cada partido es una función fija
# de su propio kickoff_at (no depende del fold), cachear features/h2h por
# match_id en disco es válido y correcto — no cambia la metodología, solo
# evita repetir trabajo ya hecho si el proceso hay que reiniciarlo. No se
# aplicó esta misma mitigación a train_logistic.py (rotation_index) porque
# ese experimento ya está cerrado (ADR-0011) y no se toca.
CACHE_PATH = os.environ.get(
    "H2H_FEATURE_CACHE_PATH",
    r"C:\Users\neyda\AppData\Local\Temp\claude\C--Users-neyda-Documents-soccer-predictions\a16ea985-6d0f-42fd-ab73-f0a86c856ab6\scratchpad\h2h_feature_cache.pkl",
)
CACHE_SAVE_EVERY = 25


def _load_cache() -> dict:
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "rb") as f:
            return pickle.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    tmp_path = CACHE_PATH + ".tmp"
    with open(tmp_path, "wb") as f:
        pickle.dump(cache, f)
    os.replace(tmp_path, CACHE_PATH)  # escritura atómica: no corromper el cache si el proceso muere a mitad de un dump


def _extract_one(session, m):
    as_of = m.kickoff_at - NEAR_KICKOFF_OFFSET
    features = build_features(session, m.id, as_of)
    h2h = head_to_head_features(session, m.id, m.home_team_id, m.away_team_id, as_of)
    return features, h2h


def build_dataset(session, matches, with_h2h: bool, cache: dict):
    x, y = [], []
    new_entries = 0
    for i, m in enumerate(matches, start=1):
        key = str(m.id)
        if key in cache:
            features, h2h = cache[key]
        else:
            try:
                features, h2h = with_retries(session, lambda m=m: _extract_one(session, m))
            except ValueError:
                continue
            cache[key] = (features, h2h)
            new_entries += 1
            if new_entries % CACHE_SAVE_EVERY == 0:
                _save_cache(cache)
        x.append(logistic.vectorize(features, h2h=h2h if with_h2h else None))
        outcome = 0 if m.home_goals > m.away_goals else (2 if m.away_goals > m.home_goals else 1)
        y.append(outcome)
        if i % COMMIT_EVERY == 0:
            session.commit()  # no-op sobre datos (solo lecturas) — cierra la transacción actual
    session.commit()
    if new_entries:
        _save_cache(cache)
    return np.array(x), np.array(y)


def main() -> int:
    session = SessionLocal()
    try:
        competition = session.query(Competition).filter_by(api_football_id=LIGA_PROFESIONAL_ARGENTINA_ID).one()
        folds = get_folds(session, competition.id)
        evaluation_run_at = datetime.now(timezone.utc)

        variants = {"logistic_no_h2h": False, "logistic_with_h2h": True}
        all_results: dict[str, list] = {name: [] for name in variants}
        last_fitted_model: dict[str, dict] = {}  # el modelo del último fold (más datos de train) es el que se serializa
        cache = _load_cache()
        if cache:
            print(f"Cache cargado desde {CACHE_PATH}: {len(cache)} partidos ya calculados.")

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

            for name, with_h2h in variants.items():
                x_train, y_train = build_dataset(session, train_matches, with_h2h, cache)
                x_eval, y_eval = build_dataset(session, eval_matches, with_h2h, cache)
                if len(x_train) < 20 or len(x_eval) < 20:
                    print(f"{name}: datos insuficientes en este fold, se omite")
                    continue
                model = logistic.fit(x_train, y_train)
                y_pred = np.array([logistic.predict_proba(model, row) for row in x_eval])
                metrics = compute_all_metrics(y_eval, y_pred)
                print(f"{name:24s} n={metrics['n_samples']:4d}  log_loss={metrics['log_loss']:.4f}  brier={metrics['brier_score']:.4f}  acc={metrics['accuracy']:.3f}")
                all_results[name].append((eval_season.year_label, metrics, y_eval, y_pred))
                last_fitted_model[name] = model

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
                # Serializa el modelo del último fold (el que usó más datos de
                # train) — ver ADR-0018, un ModelVersion debe ser cargable
                # para inferencia, no solo metadata descriptiva.
                artifact = logistic.serialize_fitted(last_fitted_model[name]) if name in last_fitted_model else None
                session.add(
                    ModelVersion(
                        name=name,
                        version_tag="v1",
                        algorithm_family="logistic",
                        training_dataset_version="v2",  # incluye 2025/2026 (ver ADR-0003 update)
                        hyperparameters={
                            "features": logistic.FEATURE_NAMES_WITH_H2H if "with_h2h" in name else logistic.FEATURE_NAMES,
                            "fitted_artifact_b64": artifact,
                            "fitted_from_fold": len(folds),
                        },
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
