import pandas as pd
import joblib
import os
import logging
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import (
    RandomForestClassifier,
    ExtraTreesClassifier,
    GradientBoostingClassifier,
    AdaBoostClassifier,
    StackingClassifier
)
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier


MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "model.pkl")
FEATURE_ORDER_PATH = os.path.join(MODEL_DIR, "feature_order.pkl")


def evaluate_model(name, model, X_train, X_test, y_train, y_test):

    start = time.time()

    model.fit(X_train, y_train)
    preds = model.predict(X_test)

    end = time.time()

    return {
        "model": name,
        "accuracy": round(accuracy_score(y_test, preds), 4),
        "precision": round(precision_score(y_test, preds, average="weighted", zero_division=0), 4),
        "recall": round(recall_score(y_test, preds, average="weighted", zero_division=0), 4),
        "f1": round(f1_score(y_test, preds, average="weighted", zero_division=0), 4),
        "time": round(end - start, 4)
    }


def train_and_evaluate(dataset_path):

    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)

    df = pd.read_csv(dataset_path)

    if "Class" not in df.columns:
        raise Exception("Dataset must contain 'Class' column")

    X = df.drop("Class", axis=1)
    y = df["Class"]

    feature_order = list(X.columns)
    joblib.dump(feature_order, FEATURE_ORDER_PATH)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    results = []
    trained_models = {}

    models = {
        "Logistic Regression": LogisticRegression(max_iter=1000),
        "Random Forest": RandomForestClassifier(n_estimators=200),
        "Extra Trees": ExtraTreesClassifier(n_estimators=200),
        "Gradient Boosting": GradientBoostingClassifier(),
        "AdaBoost": AdaBoostClassifier(),
        "SVM": SVC(probability=True),
        "KNN": KNeighborsClassifier()
    }

    for name, model in models.items():
        metrics = evaluate_model(name, model, X_train, X_test, y_train, y_test)
        results.append(metrics)
        trained_models[name] = model

    # ---------------- STACKING ----------------

    stack = StackingClassifier(
        estimators=[
            ('rf', trained_models["Random Forest"]),
            ('et', trained_models["Extra Trees"])
        ],
        final_estimator=LogisticRegression()
    )

    stack_metrics = evaluate_model("Stacking", stack, X_train, X_test, y_train, y_test)
    results.append(stack_metrics)

    # ---------------- BEST MODEL ----------------

    best = max(results, key=lambda x: x["accuracy"])
    best_name = best["model"]

    logger.info(f"Best model selected: {best_name}")

    model_objects = {**trained_models, "Stacking": stack}

    joblib.dump(model_objects[best_name], MODEL_PATH)

    return results
