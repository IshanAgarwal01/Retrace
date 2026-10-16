from fastapi import FastAPI

app = FastAPI(title="Retrace")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/hello/{name}")
def hello(name: str, excited: bool = False):
    message = f"Hello, {name}"
    if excited:
        message += "!!!"
    return {"message": message}


@app.get("/items")
def items():
    return [
        {"type": "task", "title": "Finish 2321 homework", "due": "Friday"},
        {"type": "idea", "title": "App that recovers lost thoughts", "due": None},
    ]