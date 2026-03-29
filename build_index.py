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
        name = filename.split(".")[0]

        # load image
        image = Image.open(os.path.join(image_dir, filename)).convert("RGB")

        # extract visual features
        inputs = processor(images=image, return_tensors="pt")
        with torch.no_grad():
            image_features = model.get_image_features(**inputs)
        
        # convert tensor to a flat python list for ChromaDB
        embedding = image_features.flatten().tolist()

        # load associated metadata
        with open(os.path.join(meta_dir, f"{name}.json"), "r") as f:
            metadata = json.load(f)

        # add vector to database
        collection.add(embeddings=[embedding], metadatas=[metadata], ids=[name])
        print("Added {name} to the vector database")

print("Index built successfully")
