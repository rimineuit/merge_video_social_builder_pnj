FROM python:3.11

WORKDIR /app

COPY requirements.txt /app/requirements.txt

# Dùng cache mount (BuildKit) để tăng tốc pip (không làm phình image)
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

COPY . /app

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8888"]