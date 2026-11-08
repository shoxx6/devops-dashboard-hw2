FROM python:3.12-slim AS model-build

WORKDIR /build
COPY train_model.py ./
COPY data/sms-spam-collection.zip ./data/sms-spam-collection.zip
RUN python train_model.py

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

COPY --from=model-build --chown=appuser:appuser /build/models ./models
COPY --chown=appuser:appuser app.py train_model.py ./
COPY --chown=appuser:appuser public ./public

USER appuser
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:10000/health', timeout=2)" || exit 1

CMD ["python", "app.py"]
