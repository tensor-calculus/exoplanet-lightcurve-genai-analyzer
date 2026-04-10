"""
Build ChromaDB vector index from exoplanet light curve images.
Uses CLIP to generate normalized embeddings for similarity search.
"""

import os
import json
import chromadb
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import torch

# --- Configuration ---
IMAGE_DIR = "data/images"
META_DIR = "data/metadata"
CHROMA_PATH = "./chroma_db"
COLLECTION_NAME = "exoplanets"
BATCH_SIZE = 16


def main():
    print("=" * 60)
    print("  ChromaDB Index Builder (CLIP Embeddings)")
    print("=" * 60)

    # --- Load CLIP Model ---
    print("\nLoading CLIP model (openai/clip-vit-base-patch32)...")
    model_id = "openai/clip-vit-base-patch32"
    model = CLIPModel.from_pretrained(model_id)
    processor = CLIPProcessor.from_pretrained(model_id)
    model.eval()
    print("  Model loaded.")

    # --- Initialize ChromaDB ---
    print("\nInitializing ChromaDB...")
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

    # Delete existing collection and recreate to avoid stale data
    try:
        chroma_client.delete_collection(name=COLLECTION_NAME)
        print("  Deleted existing collection.")
    except Exception:
        pass

    collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}  # Use cosine similarity
    )
    print(f"  Collection '{COLLECTION_NAME}' ready.")

    # --- Gather files ---
    image_files = sorted([
        f for f in os.listdir(IMAGE_DIR)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ])

    if not image_files:
        print(f"\nERROR: No images found in {IMAGE_DIR}/")
        print("Run fetch_data.py first to generate planet data.")
        return

    print(f"\nFound {len(image_files)} images. Processing in batches of {BATCH_SIZE}...")

    # --- Process in batches ---
    total_added = 0

    for batch_start in range(0, len(image_files), BATCH_SIZE):
        batch_files = image_files[batch_start:batch_start + BATCH_SIZE]

        batch_images = []
        batch_metas = []
        batch_ids = []

        for filename in batch_files:
            name = os.path.splitext(filename)[0]
            img_path = os.path.join(IMAGE_DIR, filename)
            meta_path = os.path.join(META_DIR, f"{name}.json")

            if not os.path.exists(meta_path):
                print(f"  SKIP {name}: no metadata file found")
                continue

            try:
                image = Image.open(img_path).convert("RGB")
                with open(meta_path, "r") as f:
                    metadata = json.load(f)

                batch_images.append(image)
                batch_metas.append(metadata)
                batch_ids.append(name)
            except Exception as e:
                print(f"  SKIP {name}: {e}")
                continue

        if not batch_images:
            continue

        # --- Generate CLIP embeddings for the batch ---
        inputs = processor(images=batch_images, return_tensors="pt", padding=True)

        with torch.no_grad():
            image_features = model.get_image_features(**inputs)

        # Handle different return types from CLIP
        if not isinstance(image_features, torch.Tensor):
            # Some versions return BaseModelOutputWithPooling
            image_features = image_features.pooler_output if hasattr(image_features, 'pooler_output') else image_features[0]

        # ✅ NORMALIZE embeddings (MUST match query-time normalization in app.py)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # Convert to list of lists
        embeddings = image_features.cpu().numpy().astype(float).tolist()

        # --- ChromaDB metadata must have string/int/float values only ---
        clean_metas = []
        for meta in batch_metas:
            clean = {}
            for k, v in meta.items():
                if v is None:
                    continue  # skip None values
                if isinstance(v, (str, int, float)):
                    clean[k] = v
                else:
                    clean[k] = str(v)
            clean_metas.append(clean)

        # --- Add batch to ChromaDB ---
        collection.add(
            embeddings=embeddings,
            metadatas=clean_metas,
            ids=batch_ids
        )

        total_added += len(batch_ids)
        print(f"  Added batch {batch_start // BATCH_SIZE + 1}: "
              f"{total_added}/{len(image_files)} planets indexed")

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(f"  Index built successfully!")
    print(f"  Total planets indexed: {total_added}")
    print(f"  ChromaDB path: {CHROMA_PATH}")
    print(f"  Collection: {COLLECTION_NAME}")
    count = collection.count()
    print(f"  Verified count: {count}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()