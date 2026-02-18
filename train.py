import pandas as pd
import joblib
import os

from sklearn.ensemble import RandomForestClassifier

MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, "model.pkl")
FEATURE_ORDER_PATH = os.path.join(MODEL_DIR, "feature_order.pkl")

print("Loading dataset...")

df = pd.read_csv("tunroid.csv")

if "Class" not in df.columns:
    raise Exception("Dataset must contain 'Class' column")

X = df.drop("Class", axis=1)
y = df["Class"]

# 🔒 CRITICAL: Save feature order for prediction safety
feature_order = list(X.columns)

if not os.path.exists(MODEL_DIR):
    os.makedirs(MODEL_DIR)

joblib.dump(feature_order, FEATURE_ORDER_PATH)

print("Training model...")

model = RandomForestClassifier(
    n_estimators=200,
    random_state=42,
    n_jobs=-1          # faster training
)

model.fit(X, y)

joblib.dump(model, MODEL_PATH)

print("Model saved successfully")
print("Feature schema saved successfully")
