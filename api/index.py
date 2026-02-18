from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from pymongo import MongoClient
import bcrypt
import joblib
import numpy as np
import os
from werkzeug.utils import secure_filename

from ml.train_models import train_and_evaluate
from ml.apk_analyzer import analyze_apk

# ---------------- PATH FIX (CRITICAL FOR VERCEL) ----------------

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static")
)

app.secret_key = "your_secret_key_here"

MODEL_PATH = os.path.join(BASE_DIR, "models", "model.pkl")
FEATURE_ORDER_PATH = os.path.join(BASE_DIR, "models", "feature_order.pkl")

# Serverless-safe writable directory
UPLOAD_FOLDER = "/tmp"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ---------------- SAFE LOADERS ----------------

def load_model():
    if not os.path.exists(MODEL_PATH):
        raise Exception("Model not found. Train the model first.")
    return joblib.load(MODEL_PATH)

def load_feature_order():
    if not os.path.exists(FEATURE_ORDER_PATH):
        raise Exception("feature_order.pkl missing. Retrain model.")
    return joblib.load(FEATURE_ORDER_PATH)

try:
    model = load_model()
    feature_order = load_feature_order()
except Exception as e:
    model = None
    feature_order = None
    print("Model load error:", str(e))


# ---------------- MongoDB ----------------

client = MongoClient(
    "mongodb+srv://Sagasri:srisaga143@box.c7q0mmf.mongodb.net/malware_project?retryWrites=true&w=majority&authSource=admin"
)

db = client["machine_learning"]
users_collection = db["users"]

# ---------------- ROUTES ----------------

@app.route("/")
def home():
    return render_template("index.html")

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

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    return render_template("dashboard.html", user=session["user"])

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

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

@app.route("/upload_dataset", methods=["POST"])
def upload_dataset():
    if "user" not in session:
        return redirect(url_for("login"))

    file = request.files["dataset"]
    filename = secure_filename(file.filename)

    dataset_path = os.path.join("/tmp", filename)
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
            filename=filename
        )

    except Exception as e:
        return f"Training Error: {str(e)}"

@app.route("/upload_apk", methods=["POST"])
def upload_apk():
    if "user" not in session:
        return redirect(url_for("login"))

    file = request.files["apk"]
    filename = secure_filename(file.filename)

    apk_path = os.path.join("/tmp", filename)
    file.save(apk_path)

    try:
        result = analyze_apk(apk_path)
        result["filename"] = filename

        return render_template(
            "apk_results.html",
            user=session["user"],
            scan_result=result
        )

    except Exception as e:
        return f"APK Analysis Error: {str(e)}"

# REQUIRED FOR VERCEL
handler = app
