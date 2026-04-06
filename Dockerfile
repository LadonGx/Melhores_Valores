FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libatomic1 openssl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN apt-get update && apt-get install -y \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libdbus-1-3 libexpat1 \
    && rm -rf /var/lib/apt/lists/*
RUN playwright install chromium
COPY . .
RUN prisma generate
CMD ["python", "execution/web_server.py"]
