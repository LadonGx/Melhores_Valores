FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y libatomic1 openssl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN prisma generate
CMD ["python", "execution/web_server.py"]
