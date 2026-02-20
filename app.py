from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from pymongo import MongoClient
import bcrypt
import joblib
import numpy as np
import os
from werkzeug.utils import secure_filename
from datetime import datetime  # ✅ Add this import

from ml.train_models import train_and_evaluate
from ml.apk_analyzer import analyze_apk

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# ---------------- CONFIG ----------------

MODEL_PATH = "models/model.pkl"
FEATURE_ORDER_PATH = "models/feature_order.pkl"
UPLOAD_FOLDER = "uploads"

# ---------------- SAFE LOADERS ----------------

def load_model():
    if not os.path.exists(MODEL_PATH):
        raise Exception("Model not found. Train the model first.")
    return joblib.load(MODEL_PATH)

def load_feature_order():
    if not os.path.exists(FEATURE_ORDER_PATH):
        raise Exception("feature_order.pkl missing. Retrain model.")
    return joblib.load(FEATURE_ORDER_PATH)

# Initialize ONCE
model = load_model()
feature_order = load_feature_order()

# ---------------- MongoDB ----------------

client = MongoClient(
    "mongodb+srv://Sagasri:srisaga143@box.c7q0mmf.mongodb.net/malware_project?retryWrites=true&w=majority&authSource=admin"
)

db = client["machine_learning"]
users_collection = db["users"]
scan_history_collection = db["scan_history"]  # ✅ Add this collection

# ---------------- ROUTES ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- ABOUT ----------------

@app.route("/about")
def about():
    return render_template("about.html")

# ---------------- CONTACT ----------------

@app.route("/contact")
def contact():
    return render_template("contact.html")

# ---------------- REGISTER ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        if not email or not password:
            return "Missing email or password"

        if users_collection.find_one({"email": email}):
            return "User already exists"

        hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

        users_collection.insert_one({
            "email": email,
            "password": hashed_pw
        })

        return redirect(url_for("login"))

    return render_template("register.html")

# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form.get("email")
        password = request.form.get("password")

        user = users_collection.find_one({"email": email})

        if not user:
            return "User not found"

        if bcrypt.checkpw(password.encode("utf-8"), user["password"]):
            session["user"] = email
            return redirect(url_for("dashboard"))

        return "Invalid password"

    return render_template("login.html")

# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    return render_template("dashboard.html", user=session["user"])

# ---------------- HISTORY PAGE ----------------

@app.route("/history")
def history():
    if "user" not in session:
        return redirect(url_for("login"))
    
    try:
        # Get scan history for current user, sorted by newest first
        scans = list(scan_history_collection.find(
            {"user": session["user"]}
        ).sort("timestamp", -1).limit(50))
        
        # Convert ObjectId to string for JSON serialization
        for scan in scans:
            scan["_id"] = str(scan["_id"])
            # Convert datetime to string if needed
            if hasattr(scan.get("timestamp"), 'strftime'):
                scan["timestamp"] = scan["timestamp"].strftime('%Y-%m-%d %H:%M:%S')
        
        return render_template("history.html", user=session["user"], scans=scans)
    
    except Exception as e:
        print(f"History error: {e}")
        # Return empty history if there's an error
        return render_template("history.html", user=session["user"], scans=[])

# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- PREDICTION API ----------------

@app.route("/predict", methods=["POST"])
def predict():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json

    try:
        vector = [data.get(f, 0) for f in feature_order]
        features = np.array([vector])

        prediction = model.predict(features)[0]

        confidence = "N/A"
        if hasattr(model, "predict_proba"):
            confidence = float(np.max(model.predict_proba(features)))

        return jsonify({
            "prediction": str(prediction),
            "confidence": round(confidence, 4) if confidence != "N/A" else confidence
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------------- DATASET TRAINING ----------------

@app.route("/upload_dataset", methods=["POST"])
def upload_dataset():

    if "user" not in session:
        return redirect(url_for("login"))

    file = request.files["dataset"]

    os.makedirs("uploads", exist_ok=True)
    dataset_path = os.path.join("uploads", file.filename)
    file.save(dataset_path)

    try:
        metrics = train_and_evaluate(dataset_path)

        global model, feature_order
        model = load_model()
        feature_order = load_feature_order()

        return render_template(
            "dataset_results.html",
            user=session["user"],
            metrics=metrics,
            filename=file.filename
        )

    except Exception as e:
        return f"Training Error: {str(e)}"


# ---------------- APK SCAN ----------------

@app.route("/upload_apk", methods=["POST"])
def upload_apk():

    if "user" not in session:
        return redirect(url_for("login"))

    file = request.files["apk"]

    os.makedirs("uploads", exist_ok=True)
    path = os.path.join("uploads", file.filename)
    file.save(path)

    try:
        result = analyze_apk(path)
        result["filename"] = file.filename
        
        # ✅ Save to scan history
        scan_record = {
            "user": session["user"],
            "filename": file.filename,
            "timestamp": datetime.now(),
            "risk_score": result.get("risk_score", 0),
            "risk_level": result.get("risk_level", "Unknown"),
            "prediction": result.get("prediction", "Unknown"),
            "permissions_count": result.get("permissions_found", 0)
        }
        
        # Add enhanced data if available
        if "enhanced" in result:
            scan_record["ensemble_prediction"] = result["enhanced"].get("ensemble_prediction", "Unknown")
            scan_record["models_count"] = len(result["enhanced"].get("models", {}))
        
        scan_history_collection.insert_one(scan_record)

        return render_template(
            "apk_results.html",
            user=session["user"],
            scan_result=result
        )

    except Exception as e:
        return f"APK Analysis Error: {str(e)}"


# ---------------- RUN ----------------

if __name__ == "__main__":
    app.run(debug=True)