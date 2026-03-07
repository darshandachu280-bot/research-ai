import os, pickle, faiss, numpy as np
from sentence_transformers import SentenceTransformer
from groq import Groq

def get_client(): return Groq(api_key=os.environ.get("GROQ_API_KEY"))
print("AI: Initializing Embedding Engine..."); embed_model = SentenceTransformer('all-MiniLM-L6-v2')

def build_vector_store(user_id, chunks):
    if not chunks: return False
    try:
        texts = [c['text'] for c in chunks]; embs = embed_model.encode(texts)
        idx = faiss.IndexFlatL2(embs.shape[1]); idx.add(np.array(embs).astype('float32'))
        os.makedirs("vectors", exist_ok=True)
        faiss.write_index(idx, f"vectors/u_{user_id}.index")
        with open(f"vectors/u_{user_id}.pkl", "wb") as f: pickle.dump(chunks, f)
        return True
    except: return False

def get_answer(user_id, question, focus_file=None, history=[]):
    idx_p = f"vectors/u_{user_id}.index"; meta_p = f"vectors/u_{user_id}.pkl"
    if not os.path.exists(idx_p): return "Upload documents first.", []
    idx = faiss.read_index(idx_p); metadata = pickle.load(open(meta_p, "rb"))
    
    vec = embed_model.encode([question]).astype('float32'); D, I = idx.search(vec, k=10)
    ctx_chunks = [metadata[i] for i in I[0] if i != -1 and i < len(metadata)]
    if focus_file: ctx_chunks = [c for c in ctx_chunks if c['filename'] == focus_file]
    context_text = "\n\n".join([f"Doc: {c['filename']}\n{c['text']}" for c in ctx_chunks[:5]])

    # Build memory string
    memory_text = "\n".join([f"Q: {h['q']}\nA: {h['a']}" for h in history])

    try:
        messages = [{"role":"system","content":f"You are a professional assistant. Answer ONLY using context. Previous Context: {memory_text}"}]
        messages.append({"role":"user","content":f"CONTEXT:\n{context_text}\n\nQ: {question}"})
        res = get_client().chat.completions.create(messages=messages, model="llama-3.1-8b-instant", temperature=0.1)
        return res.choices[0].message.content, ctx_chunks[:5]
    except Exception as e: return f"AI Error: {e}", []

def generate_document_summary(user_id):
    meta_p = f"vectors/u_{user_id}.pkl"
    if not os.path.exists(meta_p): return "No docs."
    meta = pickle.load(open(meta_p, "rb"))
    text = " ".join([c['text'] for c in meta[:8]])
    try:
        res = get_client().chat.completions.create(
            messages=[{"role":"system","content":"Summarize the highlights in bullet points."},{"role":"user","content":text[:6000]}],
            model="llama-3.1-8b-instant", temperature=0.3)
        return res.choices[0].message.content
    except: return "Error"