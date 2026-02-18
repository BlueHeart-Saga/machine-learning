import os
import re
import numpy as np
import joblib

# Silence logging (safe even if loguru missing)
os.environ["LOGURU_LEVEL"] = "ERROR"
os.environ["LOGURU_AUTOINIT"] = "False"

try:
    from loguru import logger
    logger.remove()
except Exception:
    logger = None

# ✅ SAFE IMPORT (THIS PREVENTS VERCEL CRASH)
try:
    from androguard.core.apk import APK
except Exception:
    APK = None

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

MODEL_PATH = os.path.join(BASE_DIR, "models", "model.pkl")
FEATURE_ORDER_PATH = os.path.join(BASE_DIR, "models", "feature_order.pkl")

try:
    MODEL = joblib.load(MODEL_PATH)
    FEATURE_ORDER = joblib.load(FEATURE_ORDER_PATH)
except Exception as e:
    MODEL = None
    FEATURE_ORDER = None
    print("Model load failure:", str(e))



PERMISSION_WEIGHTS = {
    "android.permission.READ_SMS": 4,
    "android.permission.SEND_SMS": 5,
    "android.permission.RECEIVE_SMS": 4,
    "android.permission.READ_CONTACTS": 3,
    "android.permission.WRITE_CONTACTS": 3,
    "android.permission.RECORD_AUDIO": 4,
    "android.permission.CAMERA": 2,
    "android.permission.READ_CALL_LOG": 4,
    "android.permission.WRITE_CALL_LOG": 4,
    "android.permission.ACCESS_FINE_LOCATION": 3,
    "android.permission.ACCESS_COARSE_LOCATION": 2,
    "android.permission.INTERNET": 1
}


SUSPICIOUS_PATTERNS = [
    "http://",
    "https://",
    "socket",
    "exec(",
    "Runtime.getRuntime",
    "DexClassLoader",
    "loadLibrary",
    "su",
    "root",
    "keylogger",
]


def analyze_apk(apk_path):

    # ✅ CRITICAL — PREVENT SERVERLESS CRASH
    if APK is None:
        return {
            "prediction": "Unavailable",
            "risk_score": 0,
            "risk_level": "APK analysis not supported on this deployment",
            "confidence": "N/A",
            "error": "androguard not available"
        }

    if MODEL is None or FEATURE_ORDER is None:
        return {
            "prediction": "Error",
            "risk_score": 0,
            "risk_level": "Model not loaded",
            "confidence": "N/A",
            "error": "ML model missing"
        }

    try:
        apk = APK(apk_path)


        permissions = apk.get_permissions()
        activities = apk.get_activities()
        services = apk.get_services()
        receivers = apk.get_receivers()
        providers = apk.get_providers()
        files = apk.get_files()

    except Exception as e:
        return {
            "prediction": "Error",
            "risk_score": 0,
            "risk_level": "Invalid APK",
            "confidence": "N/A",
            "error": str(e)
        }

    # ------------------------------------------------------------
    # Feature Vector (aligned with dataset)
    # ------------------------------------------------------------
    vector_map = {feature: 0 for feature in FEATURE_ORDER}

    for perm in permissions:
        if perm in vector_map:
            vector_map[perm] = 1

    features = np.array([[vector_map[f] for f in FEATURE_ORDER]])

    prediction = MODEL.predict(features)[0]

    probability = None
    if hasattr(MODEL, "predict_proba"):
        probability = float(np.max(MODEL.predict_proba(features)))

    # ------------------------------------------------------------
    # Risk Engine
    # ------------------------------------------------------------
    risk_score = 0
    detected_dangerous = []

    for perm in permissions:
        if perm in PERMISSION_WEIGHTS:
            risk_score += PERMISSION_WEIGHTS[perm]
            detected_dangerous.append(perm.split(".")[-1])

    # Components heuristics
    exported_risk = len(services) * 0.5 + len(receivers) * 0.3
    risk_score += exported_risk

    # Native code detection
    native_libs = [f for f in files if f.endswith(".so")]
    if native_libs:
        risk_score += 3

    # Suspicious string scanning (very effective)
    suspicious_hits = 0
    for f in files:
        lower = f.lower()
        if any(pat in lower for pat in ["dex", "payload", "shell"]):
            suspicious_hits += 1

    risk_score += suspicious_hits * 0.5

    # URLs / network indicators
    raw = " ".join(files).lower()
    urls_found = len(re.findall(r"http[s]?://", raw))
    risk_score += min(urls_found, 5) * 0.4

    # Obfuscation indicator (simple heuristic)
    short_names = sum(1 for a in activities if len(a.split(".")[-1]) <= 2)
    if short_names > 5:
        risk_score += 2

    # ------------------------------------------------------------
    # Risk Classification
    # ------------------------------------------------------------
    if risk_score >= 18:
        risk_level = "High Risk"
    elif risk_score >= 8:
        risk_level = "Medium Risk"
    else:
        risk_level = "Low Risk"

    return {
        "prediction": str(prediction),
        "risk_score": round(risk_score, 2),
        "risk_level": risk_level,
        "permissions_found": len(permissions),
        "activities": len(activities),
        "services": len(services),
        "receivers": len(receivers),
        "native_libs": len(native_libs),
        "confidence": round(probability, 4) if probability else "N/A",
        "dangerous_permissions": detected_dangerous
    }
