from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# adjust allowed origins to your GitHub Pages domain(s)
origins = [
    "https://vuhnger.github.io",
    "https://vuhnger.dev",
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

@app.get("/calendar/day/{day}")
def get_day(day: int):
    # TODO: plug in real calendar logic
    return {"day": day, "message": "placeholder"}
