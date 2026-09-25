FROM python:3.12-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY helpdesk ./helpdesk

EXPOSE 8080
CMD ["uvicorn", "helpdesk.main:app", "--host", "0.0.0.0", "--port", "8080"]
