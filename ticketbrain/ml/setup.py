"""
TicketBrain — One-time setup script.
Downloads the embedding model and saves it locally.

Run once after cloning:
    python ticketbrain/ml/setup.py
"""

from pathlib import Path
from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL  = "all-MiniLM-L6-v2"
MODELS_DIR       = Path(__file__).parent / "models"
EMBEDDING_DIR    = MODELS_DIR / "embedding_model"

MODELS_DIR.mkdir(exist_ok=True)


def download_embedding_model():
	if EMBEDDING_DIR.exists() and any(EMBEDDING_DIR.iterdir()):
		print(f"Embedding model already exists at {EMBEDDING_DIR} — skipping download.")
		return

	print(f"Downloading embedding model: {EMBEDDING_MODEL} (~90MB, one time only) ...")
	model = SentenceTransformer(EMBEDDING_MODEL)
	model.save(str(EMBEDDING_DIR))
	print(f"Model saved to {EMBEDDING_DIR}")


def check_trained_model():
	classifier_path = MODELS_DIR / "classifier.joblib"
	if not classifier_path.exists():
		print("\nNote: Trained classifier not found.")
		print("Run: python ticketbrain/ml/train.py")
	else:
		print(f"\nTrained classifier found at {classifier_path} — ready to use.")


if __name__ == "__main__":
	print("=" * 60)
	print("TicketBrain — Setup")
	print("=" * 60)
	download_embedding_model()
	check_trained_model()
	print("\nSetup complete.")
