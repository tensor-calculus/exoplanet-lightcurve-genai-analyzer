import streamlit as st
import chromadb
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import torch
from openai import OpenAI

# Setup
st.set_page_config(page_title="Exoplanet Analyzer", layout="centered")

@st.cache_resource
def load_models():

    model_id = "openai/clip-vit-base-patch32"
    model = CLIPModel.from_pretrained(model_id)
    processor = CLIPProcessor.from_pretrained(model_id)

    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    collection = chroma_client.get_collection(name="exoplanets")

    return model, processor, collection

model, processor, collection = load_models()

# UI
st.title("Exoplanet Analyzer (Lite)")
st.write("Upload a light curve image to find similar exoplanets.")

# API key for LLM
api_key = st.text_input("Enter your OpenAI API Key:", type="password")

uploaded_file = st.file_uploader("Upload Light Curve Image", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    image = Image.open(uploaded_file).convert("RGB")
    st.image(image, caption="Uploaded Image", width=300)

    if st.button("Analyze Pipeline"):

        with st.spinner("Extracting features and searching database..."):

            # CLIP Feature Extraction
            inputs = processor(images=image, return_tensors="pt")

            with torch.no_grad():
                image_features = model.get_image_features(**inputs)

            # Normalize embeddings
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            # Convert to list
            query_embedding = image_features[0].cpu().numpy().tolist()

            # Query ChromaDB
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=1
            )

            match_metadata = results["metadatas"][0][0]
            score = results["distances"][0][0]

            st.success(f"Closest match: **{match_metadata['name']}**")
            st.write(f"Similarity score: {score:.4f}")
            st.json(match_metadata)

        # Optional LLM Explanation
        if api_key:
            st.write("### Generating Explanation...")

            client = OpenAI(api_key=api_key)

            prompt = f"""
            You are an expert astronomer.
            
            Planet Name: {match_metadata['name']}
            Orbital Period: {match_metadata['period']} days
            Temperature: {match_metadata['temp']} K
            
            Explain this in 2 short paragraphs.
            """

            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}]
            )

            st.write(response.choices[0].message.content)
        else:
            st.info("Add an API key to enable AI explanation.")
