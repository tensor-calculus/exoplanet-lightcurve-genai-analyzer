# Exoplanet Lightcurve Analyzer — Project Report

## 1. Introduction

The Exoplanet Lightcurve Analyzer is a web-based application that enables users to identify exoplanets by uploading transit light curve images. It uses CLIP-based visual similarity search against a vector database of known exoplanets and provides a Retrieval-Augmented Generation (RAG) chatbot for interactive scientific discussion grounded in the matched results.

## 2. Objectives

- Fetch confirmed exoplanet data from the NASA Exoplanet Archive.
- Download real transit light curves from NASA MAST (Kepler/K2/TESS) using the `lightkurve` package, with synthetic fallback when real data is unavailable.
- Generate CLIP embeddings for each light curve image and store them in a ChromaDB vector database.
- Allow users to upload a light curve image and retrieve the most visually similar exoplanets via cosine similarity search.
- Provide a RAG-enabled chat interface powered by Google Gemini, grounded in the retrieved exoplanet metadata.

## 3. System Architecture

```
┌──────────────┐    ┌───────────────────┐    ┌─────────────┐
│  NASA TAP API │───▶│  fetch_data.py    │───▶│  data/      │
│  (metadata)   │    │  + lightkurve     │    │  images/    │
│               │    │  (light curves)   │    │  metadata/  │
└──────────────┘    └───────────────────┘    └──────┬──────┘
                                                    │
                                                    ▼
                                            ┌───────────────┐
                                            │ build_index.py│
                                            │ (CLIP + ChromaDB)
                                            └──────┬────────┘
                                                   │
                                                   ▼
                                            ┌──────────────┐
                                            │  chroma_db/  │
                                            └──────┬───────┘
                                                   │
                              ┌─────────────────────┘
                              ▼
                    ┌───────────────────┐
                    │     app.py        │
                    │  (Streamlit UI)   │
                    │                   │
                    │  • Image upload   │
                    │  • CLIP query     │
                    │  • Result cards   │
                    │  • Gemini RAG chat│
                    └───────────────────┘
```

## 4. Technology Stack

| Component         | Technology                      |
|-------------------|---------------------------------|
| Frontend          | Streamlit                       |
| Embedding Model   | CLIP ViT-B/32 (OpenAI)         |
| Vector Database   | ChromaDB (cosine similarity)    |
| LLM               | Google Gemini 2.5 Flash Lite    |
| Data Source        | NASA Exoplanet Archive (TAP API)|
| Light Curves      | lightkurve (MAST: Kepler/K2/TESS) |
| Language          | Python 3                        |

## 5. Module Descriptions

### 5.1 fetch_data.py — Data Collection

- Queries the NASA Exoplanet Archive TAP API for confirmed transiting exoplanets with known orbital period, equilibrium temperature, radius, and host star parameters.
- For each planet, attempts to download a real phase-folded transit light curve using `lightkurve` from NASA MAST (tries Kepler → K2 → TESS SPOC pipelines in order).
- If no real light curve is available, generates a synthetic transit curve using the planet's physical parameters (transit depth from Rp/Rs ratio, duration from orbital period).
- Saves each light curve as a 4×4 inch PNG image and the corresponding metadata as a JSON file.
- Classifies each planet by radius: Terrestrial, Super-Earth, Sub-Neptune, Neptune-like, or Gas Giant.

### 5.2 build_index.py — Vector Index Construction

- Loads all light curve images and their metadata from the `data/` directory.
- Generates 512-dimensional CLIP embeddings for each image using the `openai/clip-vit-base-patch32` model.
- Normalizes embeddings for cosine similarity.
- Stores embeddings and metadata in a ChromaDB persistent collection.
- Processes images in batches of 16 for efficiency.

### 5.3 app.py — Web Application

**Image Search:**
- User uploads a light curve image (PNG/JPG).
- The image is embedded using the same CLIP model.
- ChromaDB returns the top-N most similar exoplanets by cosine distance.
- Results are displayed as styled cards showing planet name, type, orbital period, temperature, radius, mass, and host star.

**RAG Chat:**
- After analysis, the matched exoplanet metadata is injected into a system prompt as context.
- The user can ask questions via a chat interface.
- Google Gemini generates responses grounded in the retrieved data.
- Conversation history is maintained across messages within a session.

## 6. Data Pipeline

```
1. Run fetch_data.py
   └─▶ Queries NASA for 55 transiting exoplanets
   └─▶ Downloads real light curves (or generates synthetic)
   └─▶ Saves to data/images/ and data/metadata/

2. Run build_index.py
   └─▶ Generates CLIP embeddings for all images
   └─▶ Stores in chroma_db/ (cosine similarity index)

3. Run app.py
   └─▶ Loads CLIP model and ChromaDB at startup
   └─▶ Serves the Streamlit web interface
```

## 7. RAG Chatbot Workflow

1. User uploads a light curve image and clicks **Analyze**.
2. CLIP encodes the image into a 512-d vector.
3. ChromaDB retrieves the top-N nearest neighbors.
4. Retrieved metadata (planet name, period, temperature, radius, type, host star) is formatted as context.
5. The context is passed as a system instruction to Gemini.
6. The user's question and chat history are sent to Gemini via the Chat API.
7. Gemini returns a grounded response referencing the specific matched planets.

## 8. How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# Step 1: Fetch data and generate light curves
python fetch_data.py

# Step 2: Build the vector index
python build_index.py

# Step 3: Launch the application
streamlit run app.py
```

**Prerequisites:**
- Python 3.10+
- A valid Google Gemini API key (stored in `api_key.txt` or entered in the sidebar)

## 9. Project Structure

```
ExoplanetAnalyzer/
├── app.py              # Streamlit web application
├── fetch_data.py       # Data collection + light curve download
├── build_index.py      # CLIP embedding + ChromaDB indexing
├── api_key.txt         # Gemini API key (not committed to git)
├── requirements.txt    # Python dependencies
├── data/
│   ├── images/         # Light curve PNG images
│   └── metadata/       # Planet metadata JSON files
└── chroma_db/          # ChromaDB persistent vector store
```

## 10. Future Scope

- Increase the planet database beyond 55 entries for broader coverage.
- Add text-based search using CLIP's text encoder (e.g., "show me hot Jupiters").
- Support multi-sector/multi-quarter light curve stitching for higher-quality real data.
- Deploy to Streamlit Community Cloud or Hugging Face Spaces for public access.
- Add comparison view to overlay uploaded light curves with matched results.
