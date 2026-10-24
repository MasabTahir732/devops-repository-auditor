"""A deliberately flawed repository fixture; never deploy it."""

from flask import Flask

import config

app = Flask(__name__)
app.config.from_object(config)


@app.get("/health")
def health():
    return {"status": "ok"}
