from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import database

SECRET_KEY = "RESEARCH_AI_EMERALD_SECRET_KEY"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_password_hash(password): return pwd_context.hash(password)
def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)
def create_access_token(data: dict):
    to_encode = data.copy()
    to_encode.update({"exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(database.get_db)):
    exc = HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None: raise exc
    except JWTError: raise exc
    user = db.query(database.User).filter(database.User.email == email).first()
    if user is None: raise exc
    return user