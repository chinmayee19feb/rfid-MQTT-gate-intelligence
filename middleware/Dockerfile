# Official Python slim image (lightweight)
FROM python:3.11-slim

# Working directory inside the container
WORKDIR /app

# Copy requirements first so Docker caches the pip install layer
# This means if only app.py changes, pip won't re-run
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all app files
COPY . .

# Port CTAgent sends data to
EXPOSE 4501

# Start Flask
CMD ["python", "app.py"]
