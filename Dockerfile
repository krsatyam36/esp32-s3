ARG PYTHON_VERSION=3.11-slim

FROM python:${PYTHON_VERSION} AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:${PYTHON_VERSION}

ARG APP_USER=appuser
ARG APP_UID=1001

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid ${APP_UID} --create-home ${APP_USER}

COPY --from=builder /root/.local /home/${APP_USER}/.local
ENV PATH=/home/${APP_USER}/.local/bin:$PATH

COPY src/ ./src/

RUN chown -R ${APP_USER}:${APP_USER} /app
USER ${APP_USER}

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request,json; r=urllib.request.urlopen('http://localhost:8000/readyz'); d=json.loads(r.read()); exit(0) if d.get('status')=='ready' else exit(1)"

CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
