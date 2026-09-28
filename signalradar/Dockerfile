FROM python:3.11-slim
WORKDIR /app
COPY signalradar/ /app/
RUN pip install --no-cache-dir -r requirements.txt
ENV PYTHONUNBUFFERED=1 SIGNAL_HOST=0.0.0.0 SIGNAL_DB=/var/lib/signalradar/cache.sqlite3 PORT=8000
RUN mkdir -p /var/lib/signalradar && chown -R 10001:10001 /var/lib/signalradar /app
USER 10001
EXPOSE 8000
CMD ["python", "server.py"]
