import schemas
import validators

from fastapi import FastAPI, HTTPException

def raise_bad_request(message):
    raise HTTPException(status_code=400, detail=message)

app = FastAPI()

@app.get("/")
def read_root():
    return "URL shortener API project"


@app.post("/url")
def create_url(url: schemas.URLBase):
    if not validators.url(url.target_url):
        raise_bad_request(message="Your provided URL is not valid")
    return f"TODO: Create database entry for: {url.target_url}"