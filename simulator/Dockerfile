FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py .
COPY ctagent_simulator.py .

# Default: demo mode pointing at the middleware container
# Override MIDDLEWARE_URL via environment variable or --url flag
ENV MIDDLEWARE_URL=http://middleware:4501

ENTRYPOINT ["python", "ctagent_simulator.py"]
CMD ["--demo"]