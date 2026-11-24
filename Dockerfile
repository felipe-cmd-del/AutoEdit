FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-por curl unzip ca-certificates \
 && curl -fsSL https://rclone.org/install.sh | bash && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
ENV DATA_DIR=/data
# atualiza o yt-dlp a cada start (sites mudam com frequência)
CMD pip install -q -U yt-dlp; uvicorn app.main:app --host 0.0.0.0 --port 8000
