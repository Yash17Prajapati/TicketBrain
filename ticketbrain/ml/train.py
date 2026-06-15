"""
TicketBrain — Classification Model Trainer

Architecture:
  Text (subject + description)
        ↓
  Embeddings  (sentence-transformers: all-MiniLM-L6-v2)
        ↓
  Classifier  (Logistic Regression — gives calibrated confidence scores)
        ↓
  Category + Confidence Score

Saved artefacts:
  models/classifier.joblib      — trained classifier
  models/label_encoder.joblib   — category name ↔ integer mapping
  models/model_config.json      — embedding model name, threshold, metadata

Run: python train.py
"""

import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
	accuracy_score,
	classification_report,
	confusion_matrix,
	f1_score,
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DATA_FILE  = BASE_DIR / "data" / "training_data.csv"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)

CLASSIFIER_PATH    = MODELS_DIR / "classifier.joblib"
LABEL_ENCODER_PATH = MODELS_DIR / "label_encoder.joblib"
CONFIG_PATH        = MODELS_DIR / "model_config.json"

# ─── Config ───────────────────────────────────────────────────────────────────
EMBEDDING_MODEL    = "all-MiniLM-L6-v2"
EMBEDDING_DIR      = MODELS_DIR / "embedding_model"
CONFIDENCE_THRESHOLD = 0.65   # below this → escalate to human agent
TEST_SIZE          = 0.20
RANDOM_STATE       = 42


# ─── Helpers ──────────────────────────────────────────────────────────────────

def load_data() -> pd.DataFrame:
	print(f"Loading data from {DATA_FILE} ...")
	df = pd.read_csv(DATA_FILE)
	print(f"  Rows loaded  : {len(df)}")
	print(f"  Categories   : {df['category'].nunique()}")
	print(f"  Sources      : {df['source'].value_counts().to_dict()}")
	return df


def combine_text(df: pd.DataFrame) -> list[str]:
	"""Combine subject + description into a single input string."""
	return (df["subject"].fillna("") + " — " + df["description"].fillna("")).tolist()


def generate_embeddings(texts: list[str], model: SentenceTransformer) -> np.ndarray:
	print(f"  Generating embeddings for {len(texts)} texts ...")
	embeddings = model.encode(
		texts,
		batch_size=64,
		show_progress_bar=True,
		convert_to_numpy=True,
	)
	print(f"  Embedding shape: {embeddings.shape}")
	return embeddings


def print_section(title: str):
	print(f"\n{'═' * 60}")
	print(f"  {title}")
	print(f"{'═' * 60}")


# ─── Main Training Flow ───────────────────────────────────────────────────────

def train():
	print_section("TicketBrain — Model Training")

	# 1. Load data
	print_section("1 / 5  Loading Data")
	df = load_data()

	# 2. Encode labels
	print_section("2 / 5  Encoding Labels")
	label_encoder = LabelEncoder()
	df["label"] = label_encoder.fit_transform(df["category"])
	categories = list(label_encoder.classes_)
	print(f"  Categories ({len(categories)}):")
	for i, cat in enumerate(categories):
		print(f"    {i}  →  {cat}")

	# 3. Generate embeddings
	print_section("3 / 5  Generating Embeddings")
	if EMBEDDING_DIR.exists() and any(EMBEDDING_DIR.iterdir()):
		print(f"  Loading embedding model from local: {EMBEDDING_DIR}")
		embedding_model = SentenceTransformer(str(EMBEDDING_DIR))
	else:
		print(f"  Embedding model not found locally. Run setup.py first.")
		print(f"  Falling back to download: {EMBEDDING_MODEL}")
		embedding_model = SentenceTransformer(EMBEDDING_MODEL)
	texts = combine_text(df)
	X = generate_embeddings(texts, embedding_model)
	y = df["label"].values

	# 4. Train / test split
	X_train, X_test, y_train, y_test = train_test_split(
		X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
	)
	print(f"  Train samples : {len(X_train)}")
	print(f"  Test samples  : {len(X_test)}")

	# 5. Train classifier
	print_section("4 / 5  Training Classifier")
	print("  Model : Logistic Regression (multi-class, calibrated probabilities)")
	classifier = LogisticRegression(
		max_iter=1000,
		random_state=RANDOM_STATE,
		solver="lbfgs",
		C=1.0,
	)
	classifier.fit(X_train, y_train)
	print("  Training complete.")

	# 6. Evaluate
	print_section("5 / 5  Evaluation")
	y_pred = classifier.predict(X_test)
	y_proba = classifier.predict_proba(X_test)
	max_confidences = y_proba.max(axis=1)

	accuracy = accuracy_score(y_test, y_pred)
	f1_weighted = f1_score(y_test, y_pred, average="weighted")
	f1_macro = f1_score(y_test, y_pred, average="macro")

	print(f"\n  Accuracy          : {accuracy:.4f}  ({accuracy * 100:.2f}%)")
	print(f"  F1 (weighted)     : {f1_weighted:.4f}")
	print(f"  F1 (macro)        : {f1_macro:.4f}")
	print(f"  Avg confidence    : {max_confidences.mean():.4f}")
	print(f"  Below threshold   : {(max_confidences < CONFIDENCE_THRESHOLD).sum()} / {len(X_test)} tickets would escalate")

	print(f"\n  Per-Category F1:\n")
	report = classification_report(
		y_test, y_pred,
		target_names=categories,
		output_dict=True,
	)
	for cat in categories:
		r = report[cat]
		bar = "█" * int(r["f1-score"] * 20)
		print(f"  {cat:<35} F1: {r['f1-score']:.3f}  {bar}")

	print(f"\n  Confusion Matrix:")
	cm = confusion_matrix(y_test, y_pred)
	header = "".join(f"{c[:4]:>6}" for c in [c[:4] for c in categories])
	print(f"  {'':35} {header}")
	for i, row in enumerate(cm):
		row_str = "".join(f"{v:>6}" for v in row)
		print(f"  {categories[i]:<35} {row_str}")

	# 7. Save model artefacts
	print_section("Saving Model Artefacts")
	joblib.dump(classifier, CLASSIFIER_PATH)
	joblib.dump(label_encoder, LABEL_ENCODER_PATH)

	config = {
		"embedding_model": EMBEDDING_MODEL,
		"confidence_threshold": CONFIDENCE_THRESHOLD,
		"categories": categories,
		"num_categories": len(categories),
		"training_samples": len(X_train),
		"test_samples": len(X_test),
		"accuracy": round(accuracy, 4),
		"f1_weighted": round(f1_weighted, 4),
		"f1_macro": round(f1_macro, 4),
	}
	with open(CONFIG_PATH, "w") as f:
		json.dump(config, f, indent=2)

	print(f"  classifier.joblib    → {CLASSIFIER_PATH}")
	print(f"  label_encoder.joblib → {LABEL_ENCODER_PATH}")
	print(f"  model_config.json    → {CONFIG_PATH}")

	print_section("Training Complete")
	print(f"  Accuracy  : {accuracy * 100:.2f}%")
	print(f"  F1 Score  : {f1_weighted:.4f}")
	print(f"  Model ready at: {MODELS_DIR}")
	print()


if __name__ == "__main__":
	train()
