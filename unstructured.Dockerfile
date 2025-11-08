FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Dipendenze di sistema + PPA per Python 3.12
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    curl wget git \
    poppler-utils \
    tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng libtesseract-dev \
    libmagic1 libgl1-mesa-glx libglib2.0-0 \
 && add-apt-repository ppa:deadsnakes/ppa \
 && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-dev python3.12-venv \
 && rm -rf /var/lib/apt/lists/*

# Utente non-root
RUN useradd -m -u 1000 notebook-user
USER notebook-user
WORKDIR /home/notebook-user

# Crea e attiva virtualenv Python 3.12
RUN python3.12 -m venv /home/notebook-user/venv
ENV PATH=/home/notebook-user/venv/bin:${PATH}
ENV VIRTUAL_ENV=/home/notebook-user/venv

# Aggiorna pip nel venv
RUN python -m pip install --upgrade pip setuptools wheel

# Clona il repo dell'API (non si pip-insta il repo; si installano i requirements)
ARG UNSTRUCTURED_API_REF=main
RUN git clone --depth 1 --branch ${UNSTRUCTURED_API_REF} https://github.com/Unstructured-IO/unstructured-api.git unstructured-api

WORKDIR /home/notebook-user/unstructured-api

# Installa i requirements lockati (compatibili con Python 3.12)
RUN python -m pip install --no-cache-dir -r requirements/base.txt

# (Se torch non vede CUDA, puoi forzare la wheel cu118)
# RUN python -m pip install --no-cache-dir --upgrade torch --index-url https://download.pytorch.org/whl/cu118

# PYTHONPATH per importare i moduli dal repo (prepline_general, scripts, ecc.)
ENV PYTHONPATH=/home/notebook-user/unstructured-api:${PYTHONPATH}

# Variabili utili
ENV UNSTRUCTURED_API_LOCAL_FILE_DIR=/documenti
ENV UNSTRUCTURED_API_LOG_LEVEL=info

EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=50s --retries=3 \
  CMD curl -f http://localhost:8000/healthcheck || exit 1

# Avvio tramite lo script del repo (gestisce uvicorn/gunicorn e init dei modelli)
ENTRYPOINT ["bash", "scripts/app-start.sh"]