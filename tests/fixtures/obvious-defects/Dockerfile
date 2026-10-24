FROM python:latest
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY --chown=10001:10001 . .
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "flask", "--app", "app", "run", "--host=0.0.0.0", "--port=8000"]
