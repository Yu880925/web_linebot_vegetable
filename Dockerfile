FROM python:3.10-slim-buster

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY rec_veg /app/rec_veg/
COPY nutri_rec /app/nutri_rec/
COPY . .

EXPOSE 5000

CMD ["python", "app.py"]