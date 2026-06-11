FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,json; r=urllib.request.urlopen('http://localhost:8000/readyz'); d=json.loads(r.read()); exit(0) if d.get('status')=='ready' else exit(1)"

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
