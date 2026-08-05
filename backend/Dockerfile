FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Railway/Render assign the port at runtime via $PORT; default to 8000 for
# `docker run` / docker-compose where nothing sets it. Shell form (not the
# exec-form JSON array) so the shell actually expands the variable.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
