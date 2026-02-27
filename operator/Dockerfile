FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd -u 10001 -m appuser
USER 10001
EXPOSE 8000
CMD ["python", "-m", "app.main"]
