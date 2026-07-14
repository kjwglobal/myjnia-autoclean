FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DATABASE_PATH=/var/data/myjnia.sqlite

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py ./server.py
COPY database ./database
COPY web ./web

RUN mkdir -p /var/data

EXPOSE 8000

CMD ["python", "server.py"]
