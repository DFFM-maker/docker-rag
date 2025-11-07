FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Evita prompt interattivi durante l'installazione
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Installa dipendenze di sistema necessarie (incluso Tesseract)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3-pip \
    python3-dev \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-ita \
    tesseract-ocr-eng \
    libtesseract-dev \
    libmagic1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Crea utente non-root
RUN useradd -m -u 1000 notebook-user

# Imposta directory di lavoro
WORKDIR /home/notebook-user

# Installa pacchetti Python come utente
USER notebook-user

# Aggiorna pip
RUN python3 -m pip install --no-cache-dir --user --upgrade pip setuptools wheel


# Installa unstructured con TUTTI gli optional: docs, GPU e API
RUN python3 -m pip install --no-cache-dir --user \
    "unstructured[all-docs,api,gpu]" \
    "gunicorn==21.2.0" \
    "uvicorn[standard]==0.24.0" \
    "pdf2image==1.16.3" \
    "python-multipart==0.0.6"

# Configura PATH per i binari dell'utente
ENV PATH=/home/notebook-user/.local/bin:${PATH}
ENV PYTHONPATH=/home/notebook-user

# Crea directory per l'applicazione
RUN mkdir -p /home/notebook-user/app

# Copia il file dell'applicazione (verrà creato nel volume)
WORKDIR /home/notebook-user

# Esponi la porta
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/healthcheck || exit 1

# Entrypoint e comando per Gunicorn (con il nome corretto)
ENTRYPOINT ["gunicorn"]
CMD ["unstructured_api.app:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "6", \
     "--timeout", "1800", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--max-requests", "200", \
     "--max-requests-jitter", "50", \
     "--log-level", "info", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]