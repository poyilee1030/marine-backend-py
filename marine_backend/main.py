from fastapi import FastAPI

app = FastAPI(title="marine-backend-py")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}
