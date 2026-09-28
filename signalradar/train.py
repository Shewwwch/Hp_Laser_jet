"""Train only when a genuine labeled dataset with both classes is available.

CSV columns: recent_count,historic_count,independent_sources,first_seen_year,label
label is 1 for expert-confirmed weak signal, 0 for mature/noise.
"""
import argparse
import csv
import json
from pathlib import Path

FEATURES = ["recent_count", "historic_count", "independent_sources", "first_seen_year"]


def train(csv_path, output):
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import classification_report, confusion_matrix
        from sklearn.model_selection import train_test_split
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        import joblib
    except ImportError as exc:
        raise SystemExit("Установите зависимости для обучения: pip install -r requirements-ml.txt") from exc
    with open(csv_path, encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    if len(rows) < 20:
        raise ValueError("Нужно минимум 20 размеченных наблюдений для отложенной проверки")
    X = [[float(row[key]) for key in FEATURES] for row in rows]
    y = [int(row["label"]) for row in rows]
    if set(y) != {0, 1} or min(y.count(0), y.count(1)) < 5:
        raise ValueError("Нужно не менее 5 экспертных примеров каждого класса")
    X_train, X_test, y_train, y_test = train_test_split(X, y, stratify=y, test_size=.25, random_state=42)
    model = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42))
    model.fit(X_train, y_train)
    predicted = model.predict(X_test)
    result = {"holdout": len(y_test), "train": len(y_train), "features": FEATURES,
              "classification_report": classification_report(y_test, predicted, labels=[0, 1], output_dict=True, zero_division=0),
              "confusion_matrix": confusion_matrix(y_test, predicted, labels=[0, 1]).tolist(),
              "warning": "Метрика относится только к предоставленной разметке и отложенной выборке; проверьте отсутствие утечки между близкими технологиями."}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": FEATURES}, output)
    output.with_suffix(".metrics.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv")
    parser.add_argument("--output", default="data/classifier.joblib")
    args = parser.parse_args()
    train(args.csv, args.output)
