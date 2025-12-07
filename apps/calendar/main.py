from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins = [
    "https://vuhnger.dev",
    "https://vuhnger.github.io",
    "https://api.vuhnger.dev",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/calendar/health")
def health():
    return {"status": "ok"}
