import os
import json
import chromadb
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import torch

print("Loading CLIP model...")
model_id = "openai/clip-vit-base-patch32"
model = CLIPModel.from_pretrained(model_id)
processor = CLIPProcessor.from_pretrained(model_id)

print("Initializing ChromaDB...")
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="exoplanets")

image_dir = "data/images"
meta_dir = "data/metadata"

print("Generating emebddings and building index...")
for filename in os.listdir(image_dir):
    if filename.endswith(".png"):
        try:
            name = filename.split(".")[0]

            # load image
            image = Image.open(os.path.join(image_dir, filename)).convert("RGB")

            # extract visual features
            inputs = processor(images=image, return_tensors="pt")
            with torch.no_grad():
                image_features = model.get_image_features(**inputs)

            # normalize embeddings
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            # convert to list
            embedding = image_features[0].cpu().numpy().tolist()

            # sanity check
            if not isinstance(embedding, list) or len(embedding) == 0:
                raise ValueError("Invalid embedding")
            
            # load metadata
            meta_path = os.path.join(meta_dir, f"{name}.json")
            with open(meta_path, "r") as f:
                metadata = json.load(f)
            
            doc_id = str(name)

            # add to DB
            collection.add(
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[doc_id]
            )

            print(f"Added {name} ✅")

        except Exception as e:
            print(f"Error processing {filename}: {e}")
            
print("Index built successfully")
