FROM python:3.12-slim-trixie

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

# Copy the application
COPY . .

EXPOSE 9000

CMD ["python", "app.py"]
