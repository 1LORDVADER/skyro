FROM python:3.12-slim
WORKDIR /vault33
COPY . .
CMD ["python", "vault33.py"]
