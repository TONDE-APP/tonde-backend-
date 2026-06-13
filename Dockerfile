FROM python:3.12-slim

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Copier UNIQUEMENT requirements.txt en premier ──────────────────
# Docker met cette couche en cache tant que requirements.txt ne change pas.
# Les prochains builds ne retéléchargent rien si requirements.txt est identique.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copier le reste du code ─────────────────────────────────────────
# Cette couche change souvent, mais elle est rapide (pas de pip install)
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
