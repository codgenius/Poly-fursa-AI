FROM python:3.12-slim-trixie

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

# Copy the application
COPY . .

EXPOSE 3001

CMD ["python", "app.py"]
