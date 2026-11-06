FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libseccomp2 && rm -rf /var/lib/apt/lists/*
RUN groupadd --system app && useradd --system --gid app --uid 10001 app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Source paths above are copied as directories; ensure migration and runtime imports work.
RUN mkdir -p /data /backups && chown -R app:app /data /backups /srv/app
USER app
CMD ["uvicorn", "app.web:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
