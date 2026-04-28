# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set work directory
WORKDIR /app

# Install system dependencies
# Removed default-libmysqlclient-dev and pkg-config as they are no longer needed
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    python3-dev \
    musl-dev \
    && apt-get clean

# Copy requirements file
COPY requirements.txt /app/

# Install dependencies
RUN pip install --upgrade pip

# Install CPU-specific torch to avoid downloading 2GB+ of unused NVIDIA/CUDA libraries
# This significantly speeds up the build and reduces image size
RUN pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu

# Install the rest of the requirements
RUN pip install -r requirements.txt

# Copy project
COPY . /app/

# Expose port
EXPOSE 8000

# Run migrations and start server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
