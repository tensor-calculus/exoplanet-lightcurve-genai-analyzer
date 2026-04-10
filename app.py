import streamlit as st
import chromadb
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import torch
import google.generativeai as genai
import os

# --- Page Config ---
st.set_page_config(
    page_title="Exoplanet Lightcurve Analyzer",
    page_icon="🪐",
    layout="wide"
)

# --- Custom CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    .stApp {
        font-family: 'Inter', sans-serif;
    }

    /* Hero header */
    .hero-title {
        font-size: 2.4rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .hero-subtitle {
        font-size: 1.05rem;
        color: #8892a4;
        margin-bottom: 1.5rem;
    }

    /* Planet result card */
    .planet-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
        border: 1px solid rgba(102, 126, 234, 0.3);
        border-radius: 16px;
        padding: 1.4rem;
        margin-bottom: 1rem;
        color: #e0e0e0;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .planet-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.2);
    }
    .planet-name {
        font-size: 1.3rem;
        font-weight: 700;
        color: #667eea;
        margin-bottom: 0.5rem;
    }
    .planet-type {
        display: inline-block;
        background: rgba(102, 126, 234, 0.2);
        border: 1px solid rgba(102, 126, 234, 0.4);
        border-radius: 20px;
        padding: 0.2rem 0.7rem;
        font-size: 0.8rem;
        color: #a0b4f0;
        margin-bottom: 0.6rem;
    }
    .planet-stat {
        display: inline-block;
        margin-right: 1.2rem;
        margin-bottom: 0.3rem;
    }
    .stat-label {
        font-size: 0.72rem;
        color: #8892a4;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .stat-value {
        font-size: 1.05rem;
        font-weight: 600;
        color: #d0d8f0;
    }
    .similarity-badge {
        float: right;
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        border-radius: 12px;
        padding: 0.3rem 0.8rem;
        font-weight: 600;
        font-size: 0.85rem;
        color: white;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f0c29 0%, #1a1a2e 50%, #16213e 100%);
    }
    section[data-testid="stSidebar"] .stMarkdown {
        color: #c0c8e0;
    }

    /* Chat messages */
    .stChatMessage {
        border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)


# --- Load Models (cached) ---
@st.cache_resource
def load_clip():
    model_id = "openai/clip-vit-base-patch32"
    model = CLIPModel.from_pretrained(model_id)
    processor = CLIPProcessor.from_pretrained(model_id)
    model.eval()
    return model, processor


@st.cache_resource
def load_chroma():
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    collection = chroma_client.get_collection(name="exoplanets")
    return collection


# --- Initialize ---
clip_model, clip_processor = load_clip()
collection = load_chroma()

# --- Session State ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "rag_context" not in st.session_state:
    st.session_state.rag_context = None
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False


# --- Sidebar ---
with st.sidebar:
    st.markdown("## ⚙️ Settings")

    # API key: try file first, then input
    default_key = ""
    if os.path.exists("api_key.txt"):
        with open("api_key.txt", "r") as f:
            default_key = f.read().strip()

    api_key = st.text_input(
        "Gemini API Key",
        value=default_key,
        type="password",
        help="Required for AI chat. Loaded from api_key.txt if present."
    )

    n_results = st.slider("Number of matches", 1, 10, 3)

    st.markdown("---")
    st.markdown(f"**Database:** {collection.count()} planets")
    st.markdown("**Model:** CLIP ViT-B/32")
    st.markdown("**LLM:** Gemini 2.5 Flash Lite")

    st.markdown("---")
    st.markdown(
        "<div style='font-size:0.75rem; color:#667;'>"
        "Data sourced from NASA Exoplanet Archive.<br>"
        "Light curves from Kepler/TESS via MAST,<br>"
        "with synthetic fallback when unavailable."
        "</div>",
        unsafe_allow_html=True
    )


# --- Main UI ---
st.markdown('<div class="hero-title">🪐 Exoplanet Lightcurve Analyzer</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-subtitle">'
    'Upload a light curve image to find similar exoplanets using AI-powered visual similarity search, '
    'then chat with an AI astronomer about your results.'
    '</div>',
    unsafe_allow_html=True
)

# --- Layout ---
col_upload, col_results = st.columns([1, 2])

with col_upload:
    st.markdown("### 📤 Upload Light Curve")
    uploaded_file = st.file_uploader(
        "Choose an image",
        type=["png", "jpg", "jpeg"],
        label_visibility="collapsed"
    )

    if uploaded_file is not None:
        image = Image.open(uploaded_file).convert("RGB")
        st.image(image, caption="Your uploaded light curve", use_container_width=True)

        analyze_btn = st.button("🔍 Analyze", type="primary", use_container_width=True)
    else:
        analyze_btn = False


def get_embedding(image):
    """Get normalized CLIP embedding for an image."""
    inputs = clip_processor(images=image, return_tensors="pt")
    with torch.no_grad():
        features = clip_model.get_image_features(**inputs)

    # Handle different return types from CLIP
    if not isinstance(features, torch.Tensor):
        features = features.pooler_output if hasattr(features, 'pooler_output') else features[0]

    # Normalize (matches build_index.py normalization)
    features = features.squeeze(0)
    features = features / features.norm(dim=-1, keepdim=True)
    return features.cpu().numpy().astype(float).reshape(-1).tolist()


def render_planet_card(meta, distance, rank):
    """Render a planet result as a styled card."""
    similarity = max(0, 1 - distance) * 100  # cosine distance -> similarity %

    name = meta.get("name", "Unknown")
    ptype = meta.get("type", "Unknown")
    period = meta.get("period", "N/A")
    temp = meta.get("temp", "N/A")
    radius = meta.get("radius_earth", "N/A")
    star = meta.get("host_star", "N/A")
    mass = meta.get("mass_earth", "N/A")

    card_html = f"""
    <div class="planet-card">
        <div class="similarity-badge">#{rank} · {similarity:.1f}% match</div>
        <div class="planet-name">{name}</div>
        <div class="planet-type">{ptype}</div>
        <br>
        <div class="planet-stat">
            <span class="stat-label">Period</span><br>
            <span class="stat-value">{period} days</span>
        </div>
        <div class="planet-stat">
            <span class="stat-label">Temperature</span><br>
            <span class="stat-value">{temp} K</span>
        </div>
        <div class="planet-stat">
            <span class="stat-label">Radius</span><br>
            <span class="stat-value">{radius} R⊕</span>
        </div>
        <div class="planet-stat">
            <span class="stat-label">Mass</span><br>
            <span class="stat-value">{mass} M⊕</span>
        </div>
        <div class="planet-stat">
            <span class="stat-label">Host Star</span><br>
            <span class="stat-value">{star}</span>
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)


# --- Analysis ---
with col_results:
    if analyze_btn and uploaded_file is not None:
        with st.spinner("🔭 Analyzing light curve with CLIP..."):
            query_embedding = get_embedding(image)

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )

        st.markdown("### 🔍 Similar Exoplanets")

        if results["metadatas"][0]:
            # Store context for RAG chat
            st.session_state.rag_context = results["metadatas"][0]
            st.session_state.analysis_done = True
            # Clear previous chat when new analysis is done
            st.session_state.chat_history = []

            for i, (meta, dist) in enumerate(
                zip(results["metadatas"][0], results["distances"][0])
            ):
                render_planet_card(meta, dist, i + 1)
        else:
            st.error("No matches found. Make sure the database is built (run build_index.py).")

    elif st.session_state.analysis_done and st.session_state.rag_context:
        # Re-render previous results
        st.markdown("### 🔍 Similar Exoplanets")
        for i, meta in enumerate(st.session_state.rag_context):
            render_planet_card(meta, 0.0, i + 1)
    else:
        st.markdown("### 🔍 Results")
        st.info("Upload a light curve image and click **Analyze** to find similar exoplanets.")


# --- RAG Chat Section ---
st.markdown("---")
st.markdown("### 💬 Chat with AI Astronomer")

if not st.session_state.analysis_done:
    st.info("Analyze an image first to unlock the chat. The AI will give responses grounded in your matched exoplanet data.")
elif not api_key:
    st.warning("Enter your Gemini API key in the sidebar to enable chat.")
else:
    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    user_input = st.chat_input("Ask about the matched exoplanets...")

    if user_input:
        # Display user message
        with st.chat_message("user"):
            st.markdown(user_input)
        st.session_state.chat_history.append({"role": "user", "content": user_input})

        # Build grounded system prompt with RAG context
        context_parts = []
        for i, meta in enumerate(st.session_state.rag_context):
            parts = [f"Match #{i+1}: {meta.get('name', 'Unknown')}"]
            for key, val in meta.items():
                if key != "name":
                    parts.append(f"  {key}: {val}")
            context_parts.append("\n".join(parts))

        rag_context_text = "\n\n".join(context_parts)

        system_prompt = f"""You are an expert astronomer and exoplanet scientist. 
You are helping a user analyze exoplanet light curves.

The user uploaded a light curve image and our similarity search found these matching exoplanets:

{rag_context_text}

IMPORTANT RULES:
- Ground your responses in the above data. Reference specific planet names, periods, temperatures, etc.
- When comparing planets, use the actual values from the data above.
- If the user asks something outside the scope of these planets, you may use your general astronomy knowledge but clearly state when you are going beyond the matched data.
- Be educational, engaging, and scientifically accurate.
- Use appropriate units (days for period, Kelvin for temperature, Earth radii for radius, etc.)
- Keep responses concise but informative (2-4 paragraphs max unless asked for more detail)."""

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(st.session_state.chat_history)

        # Call Gemini
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel(
                        model_name="gemini-2.5-flash-lite",
                        system_instruction=system_prompt,
                        generation_config=genai.GenerationConfig(
                            temperature=0.7,
                            max_output_tokens=800,
                        ),
                    )
                    # Convert chat history to Gemini format
                    gemini_history = []
                    for msg in st.session_state.chat_history[:-1]:  # exclude latest user msg
                        role = "model" if msg["role"] == "assistant" else "user"
                        gemini_history.append({"role": role, "parts": [msg["content"]]})
                    chat = model.start_chat(history=gemini_history)
                    response = chat.send_message(user_input)
                    reply = response.text
                    st.markdown(reply)
                    st.session_state.chat_history.append(
                        {"role": "assistant", "content": reply}
                    )
                except Exception as e:
                    st.error(f"Gemini API error: {e}")

    # Clear chat button
    if st.session_state.chat_history:
        if st.button("🗑️ Clear Chat"):
            st.session_state.chat_history = []
            st.rerun()
