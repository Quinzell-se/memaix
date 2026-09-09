FROM python:3.12-slim
WORKDIR /app
COPY login-app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY login-app/app.py .
COPY login-app/auth.py .
COPY login-app/approved_clients.py .
COPY login-app/templates/ templates/
COPY gateway/src/memaix_gateway/__init__.py i18n_pkg/memaix_gateway/__init__.py
COPY gateway/src/memaix_gateway/i18n/ i18n_pkg/memaix_gateway/i18n/
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "3000"]
