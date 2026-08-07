FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set working directory
WORKDIR /code

# Copy requirements and install
COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# Install Playwright browser binaries inside docker
RUN playwright install chromium

# Copy project code
COPY . /code

# Expose port (FastAPI default)
EXPOSE 8000

# Start FastAPI application dynamically binding to Railway's PORT env variable
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
