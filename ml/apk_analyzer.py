import os
import re
import numpy as np
import joblib
import hashlib
from collections import Counter

# Silence logging
os.environ["LOGURU_LEVEL"] = "ERROR"
os.environ["LOGURU_AUTOINIT"] = "False"

try:
    from loguru import logger
    logger.remove()
except Exception:
    logger = None

# Safe import for Androguard
try:
    from androguard.core.apk import APK
except Exception:
    APK = None

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# Multiple model paths
MODELS = {
    'random_forest': os.path.join(BASE_DIR, "models", "random_forest.pkl"),
    'xgboost': os.path.join(BASE_DIR, "models", "xgboost.pkl"),
    'svm': os.path.join(BASE_DIR, "models", "svm.pkl"),
    'neural_network': os.path.join(BASE_DIR, "models", "neural_network.pkl")
}

FEATURE_ORDER_PATH = os.path.join(BASE_DIR, "models", "feature_order.pkl")

# Load main model (for backward compatibility)
try:
    MAIN_MODEL = joblib.load(os.path.join(BASE_DIR, "models", "model.pkl"))
except Exception:
    MAIN_MODEL = None

# Load all models
MODEL_OBJECTS = {}
for model_name, model_path in MODELS.items():
    try:
        if os.path.exists(model_path):
            MODEL_OBJECTS[model_name] = joblib.load(model_path)
    except Exception as e:
        print(f"Failed to load {model_name}: {str(e)}")

try:
    FEATURE_ORDER = joblib.load(FEATURE_ORDER_PATH)
except Exception as e:
    FEATURE_ORDER = None
    print("Feature order load failure:", str(e))

# Enhanced permission weights
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
    "android.permission.INTERNET": 1,
    "android.permission.INSTALL_PACKAGES": 5,
    "android.permission.DELETE_PACKAGES": 5,
    "android.permission.ACCESS_SUPERUSER": 5,
    "android.permission.READ_LOGS": 4,
    "android.permission.WRITE_SETTINGS": 3,
    "android.permission.SYSTEM_ALERT_WINDOW": 3,
    "android.permission.GET_TASKS": 3,
    "android.permission.KILL_BACKGROUND_PROCESSES": 4,
    "android.permission.ACCESS_NETWORK_STATE": 1
}

def analyze_apk(apk_path):
    """
    Main analysis function - COMPATIBLE with existing template
    Returns structure expected by apk_results.html
    """
    
    # Check if Androguard is available
    if APK is None:
        return {
            "prediction": "Unavailable",
            "risk_score": 0,
            "risk_level": "APK analysis not supported on this deployment",
            "confidence": "N/A",
            "error": "androguard not available",
            "filename": os.path.basename(apk_path),
            "permissions_found": 0,
            "activities": 0,
            "services": 0,
            "receivers": 0,
            "native_libs": 0,
            "dangerous_permissions": []
        }

    try:
        apk = APK(apk_path)
        
        # Basic APK information
        permissions = apk.get_permissions()
        activities = apk.get_activities()
        services = apk.get_services()
        receivers = apk.get_receivers()
        providers = apk.get_providers()
        files = apk.get_files()
        
        # Package info (for enhanced features)
        package_name = apk.get_package() or "Unknown"
        version_name = apk.get_androidversion_name() or "Unknown"
        min_sdk = apk.get_min_sdk_version() or "Unknown"
        target_sdk = apk.get_target_sdk_version() or "Unknown"
        
        # Calculate APK hash
        try:
            with open(apk_path, 'rb') as f:
                apk_hash = hashlib.sha256(f.read()).hexdigest()
        except:
            apk_hash = "Unknown"
        
    except Exception as e:
        return {
            "prediction": "Error",
            "risk_score": 0,
            "risk_level": "Invalid APK",
            "confidence": "N/A",
            "error": str(e),
            "filename": os.path.basename(apk_path),
            "permissions_found": 0,
            "activities": 0,
            "services": 0,
            "receivers": 0,
            "native_libs": 0,
            "dangerous_permissions": []
        }

    # ------------------------------------------------------------
    # Feature Vector (for ML model)
    # ------------------------------------------------------------
    prediction = "unknown"
    probability = None
    
    if FEATURE_ORDER and MAIN_MODEL:
        try:
            vector_map = {feature: 0 for feature in FEATURE_ORDER}
            for perm in permissions:
                if perm in vector_map:
                    vector_map[perm] = 1
            
            features = np.array([[vector_map[f] for f in FEATURE_ORDER]])
            prediction = str(MAIN_MODEL.predict(features)[0])
            
            if hasattr(MAIN_MODEL, "predict_proba"):
                probability = float(np.max(MAIN_MODEL.predict_proba(features)))
                probability = round(probability, 4)
        except Exception as e:
            print(f"Prediction error: {e}")
            prediction = "error"

    # ------------------------------------------------------------
    # Risk Engine
    # ------------------------------------------------------------
    risk_score = 0.0
    detected_dangerous = []
    
    # Permission-based risk
    for perm in permissions:
        if perm in PERMISSION_WEIGHTS:
            risk_score += float(PERMISSION_WEIGHTS[perm])
            detected_dangerous.append(perm)

    # Components heuristics
    exported_risk = float(len(services)) * 0.5 + float(len(receivers)) * 0.3
    risk_score += exported_risk

    # Native code detection
    native_libs = [f for f in files if f.endswith(".so")]
    if native_libs:
        risk_score += 3.0

    # Suspicious string scanning
    suspicious_hits = 0
    for f in files:
        lower = f.lower()
        if any(pat in lower for pat in ["dex", "payload", "shell"]):
            suspicious_hits += 1
    risk_score += float(suspicious_hits) * 0.5

    # URLs detection
    raw = " ".join(files).lower()
    urls_found = len(re.findall(r"http[s]?://", raw))
    risk_score += float(min(urls_found, 5)) * 0.4

    # Obfuscation indicator
    short_names = sum(1 for a in activities if len(a.split(".")[-1]) <= 2)
    if short_names > 5:
        risk_score += 2.0

    # ------------------------------------------------------------
    # Get predictions from multiple models (enhanced)
    # ------------------------------------------------------------
    model_predictions = {}
    ensemble_prediction = "unknown"
    ensemble_confidence = 0.0
    
    if MODEL_OBJECTS and FEATURE_ORDER:
        try:
            vector_map = {feature: 0 for feature in FEATURE_ORDER}
            for perm in permissions:
                if perm in vector_map:
                    vector_map[perm] = 1
            
            feature_vector = np.array([[vector_map[f] for f in FEATURE_ORDER]])
            
            for model_name, model in MODEL_OBJECTS.items():
                try:
                    pred = str(model.predict(feature_vector)[0])
                    proba = None
                    if hasattr(model, 'predict_proba'):
                        proba = float(np.max(model.predict_proba(feature_vector)))
                        proba = round(proba, 4)
                    
                    model_predictions[model_name] = {
                        'prediction': pred,
                        'confidence': proba
                    }
                except Exception as e:
                    model_predictions[model_name] = {
                        'prediction': 'Error',
                        'confidence': None
                    }
            
            # Calculate ensemble prediction
            malware_votes = 0
            total_models = len(model_predictions)
            for pred_data in model_predictions.values():
                if pred_data.get('prediction') == 'malware':
                    malware_votes += 1
            
            if total_models > 0:
                ensemble_prediction = "malware" if malware_votes > total_models/2 else "benign"
                ensemble_confidence = float(malware_votes) / float(total_models)
                ensemble_confidence = round(ensemble_confidence, 4)
        except Exception as e:
            print(f"Ensemble error: {e}")

    # ------------------------------------------------------------
    # Risk Classification
    # ------------------------------------------------------------
    if risk_score >= 18:
        risk_level = "High Risk"
    elif risk_score >= 8:
        risk_level = "Medium Risk"
    else:
        risk_level = "Low Risk"

    # Extract URLs for display
    urls_list = re.findall(r"https?://[^\s]+", raw)[:10]

    # ------------------------------------------------------------
    # COMPATIBLE RETURN STRUCTURE (with enhanced fields)
    # ------------------------------------------------------------
    result = {
        # Basic fields (required by template)
        "filename": os.path.basename(apk_path),
        "prediction": prediction,
        "risk_score": round(float(risk_score), 2),
        "risk_level": risk_level,
        "confidence": probability if probability is not None else "N/A",
        "permissions_found": len(permissions),
        "activities": len(activities),
        "services": len(services),
        "receivers": len(receivers),
        "native_libs": len(native_libs),
        "dangerous_permissions": [p.split('.')[-1] for p in detected_dangerous[:15]],
        
        # Enhanced fields (for new template)
        "enhanced": {
            "package_info": {
                "name": str(package_name),
                "version": str(version_name),
                "min_sdk": str(min_sdk),
                "target_sdk": str(target_sdk),
                "hash": str(apk_hash)
            },
            "permissions": {
                "total": len(permissions),
                "dangerous": len(detected_dangerous),
                "normal": max(0, len(permissions) - len(detected_dangerous)),
                "signature": 0,
                "dangerous_list": detected_dangerous[:20]
            },
            "components": {
                "activities": len(activities),
                "services": len(services),
                "receivers": len(receivers),
                "providers": len(providers),
                "total": len(activities) + len(services) + len(receivers) + len(providers)
            },
            "files": {
                "total": len(files),
                "dex": len([f for f in files if f.endswith('.dex')]),
                "native_libs": len(native_libs),
                "assets": len([f for f in files if f.startswith('assets/')]),
                "urls_found": urls_found
            },
            "risk_factors": {
                "permissions": min(float(len(detected_dangerous) * 2), 30.0),
                "components": min(float(len(services) * 0.5 + len(receivers) * 0.3), 15.0),
                "native_code": min(float(len(native_libs) * 2), 15.0),
                "network_indicators": min(float(urls_found) * 1.5, 15.0),
                "obfuscation": min(float(short_names), 15.0)
            },
            "models": model_predictions,
            "ensemble_prediction": ensemble_prediction,
            "ensemble_confidence": ensemble_confidence,
            "urls_found": urls_list,
            "obfuscation_score": short_names
        }
    }
    
    return result