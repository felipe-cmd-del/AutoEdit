FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-por curl unzip ca-certificates \
 && curl -fsSL https://rclone.org/install.sh | bash && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
# PyTorch só CPU (bem menor)
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# baixa o modelo de visão durante o build
ENV HF_HOME=/srv/models
RUN python -c "import open_clip; open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')"
COPY app ./app
ENV DATA_DIR=/data
# atualiza o yt-dlp a cada start (sites mudam com frequência)
CMD pip install -q -U yt-dlp; uvicorn app.main:app --host 0.0.0.0 --port 8000
