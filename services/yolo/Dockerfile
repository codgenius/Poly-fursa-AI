FROM python:3.12-slim-trixie

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y libgl1-mesa-dev libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY torch-requirements.txt .
COPY requirements.txt .

RUN pip install --no-cache-dir -r torch-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
# Copy the application last
COPY . .

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
