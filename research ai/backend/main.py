import database, auth, utils, rag_engine, json, os, shutil
from dotenv import load_dotenv
load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY", "")

from typing import List, Optional
from fastapi import FastAPI, Depends, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

# Corrected FPDF import for fpdf2
try:
    from fpdf import FPDF
except ImportError:
    from fpdf2 import FPDF

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Mount uploads folder
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

def safe_pdf_str(s):
    return s.encode('latin-1', 'ignore').decode('latin-1') if s else ""

# --- BACKGROUND TASKS ---
def run_proc(uid, db_factory):
    db = db_factory()
    try:
        docs = db.query(database.Document).filter(database.Document.user_id==uid, database.Document.status=="processing").all()
        for d in docs: d.status = "completed"
        db.commit()
        all_docs = db.query(database.Document).filter(database.Document.user_id==uid, database.Document.status=="completed").all()
        chunks = []
        for d in all_docs:
            fpath = f"uploads/{uid}_{d.filename}"
            if os.path.exists(fpath):
                raw = utils.extract_text(fpath, os.path.splitext(d.filename)[1].lower())
                for t, p in raw: chunks.extend(utils.split_text(t, p, d.filename))
        if chunks: rag_engine.build_vector_store(uid, chunks)
    except Exception as e: print(f"AI Task Error: {e}")
    finally: db.close()

# --- AUTH ROUTES ---
@app.post("/register")
def register(name:str=Form(...), email:str=Form(...), password:str=Form(...), db:Session=Depends(database.get_db)):
    if db.query(database.User).filter(database.User.email==email).first(): raise HTTPException(400, "User exists")
    db.add(database.User(name=name, email=email, hashed_password=auth.get_password_hash(password)))
    db.commit()
    return {"msg": "ok"}

@app.post("/login")
def login(email:str=Form(...), password:str=Form(...), db:Session=Depends(database.get_db)):
    u = db.query(database.User).filter(database.User.email==email).first()
    if not u or not auth.verify_password(password, u.hashed_password): raise HTTPException(401, "Invalid Login")
    return {"access_token": auth.create_access_token({"sub": u.email}), "token_type": "bearer"}

@app.get("/me")
def me(u: database.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    try:
        doc_count = db.query(database.Document).filter(database.Document.user_id == u.id).count()
        chat_count = db.query(database.ChatMessage).filter(database.ChatMessage.user_id == u.id).count()
        joined = u.created_at.strftime("%B %Y") if u.created_at else "Feb 2026"
        return {
            "name": u.name, "email": u.email, "role": u.role or "Researcher",
            "profile_pic": u.profile_pic, "doc_count": doc_count, "chat_count": chat_count,
            "joined": joined, "personality": u.ai_personality or "Technical Expert"
        }
    except Exception as e:
        print(f"Error in /me: {e}")
        raise HTTPException(500)

@app.post("/update-profile")
def update_profile(name:str=Form(...), role:str=Form(...), password:str=Form(None), pic:UploadFile=File(None), u:database.User=Depends(auth.get_current_user), db:Session=Depends(database.get_db)):
    u.name, u.role = name, role
    if password: u.hashed_password = auth.get_password_hash(password)
    if pic:
        fpath = f"uploads/avatar_{u.id}{os.path.splitext(pic.filename)[1]}"
        with open(fpath, "wb") as b: shutil.copyfileobj(pic.file, b)
        u.profile_pic = f"/{fpath}"
    db.commit(); return {"msg": "ok"}

# --- DATA ROUTES ---
@app.post("/upload")
def upload(bt: BackgroundTasks, files: List[UploadFile] = File(...), u=Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    for f in files:
        fpath = f"uploads/{u.id}_{f.filename}"
        with open(fpath, "wb") as b: shutil.copyfileobj(f.file, b)
        db.add(database.Document(filename=f.filename, user_id=u.id, status="processing"))
    db.commit(); bt.add_task(run_proc, u.id, database.SessionLocal); return {"msg": "ok"}

@app.get("/documents")
def docs(u: database.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    return db.query(database.Document).filter(database.Document.user_id == u.id).all()

@app.delete("/documents/{doc_id}")
def delete_doc(doc_id: int, u: database.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    doc = db.query(database.Document).filter(database.Document.id == doc_id, database.Document.user_id == u.id).first()
    if doc: db.delete(doc); db.commit(); return {"msg": "ok"}
    raise HTTPException(404)

@app.post("/ask")
def ask(question: str = Form(...), focus_file: str = Form(None), u=Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    ans, src = rag_engine.get_answer(u.id, question, focus_file)
    db.add(database.ChatMessage(user_id=u.id, question=question, answer=ans, sources=json.dumps(src)))
    db.commit(); return {"answer": ans, "sources": src}

@app.get("/chat-history")
def hist(u: database.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    c = db.query(database.ChatMessage).filter(database.ChatMessage.user_id == u.id).order_by(database.ChatMessage.created_at.asc()).all()
    return [{"question": x.question, "answer": x.answer} for x in c]

@app.delete("/chat-history")
def clear(u: database.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    db.query(database.ChatMessage).filter(database.ChatMessage.user_id == u.id).delete()
    db.commit(); return {"msg": "ok"}

@app.post("/summarize")
def summarize(u: database.User = Depends(auth.get_current_user)):
    return {"summary": rag_engine.generate_document_summary(u.id)}

@app.get("/export-pdf")
def export_pdf(u: database.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    chats = db.query(database.ChatMessage).filter(database.ChatMessage.user_id == u.id).all()
    pdf = FPDF(); pdf.add_page(); pdf.set_font("helvetica", "B", 16); pdf.cell(0, 10, "Research Report", ln=True, align='C')
    for c in chats:
        pdf.set_font("helvetica", "B", 11); pdf.multi_cell(0, 8, txt=f"Q: {safe_pdf_str(c.question)}")
        pdf.set_font("helvetica", "", 10); pdf.multi_cell(0, 7, txt=f"A: {safe_pdf_str(c.answer)}"); pdf.ln(5)
    fpath = f"uploads/rep_{u.id}.pdf"; pdf.output(fpath); return FileResponse(fpath, filename="Report.pdf")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)