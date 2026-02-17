FROM python:3.10-slim

WORKDIR /app

ENV BOAT_RIDE_DATA_DIR=/app/data

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source and install package
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e .

# Pre-download coastline shapefile into the image so first request isn't slow
RUN python -c "from boat_ride.geo.shoreline import ShorelineData; ShorelineData.get().coastline; print('Coastline cached')"

EXPOSE 10000

CMD sh -c "gunicorn boat_ride.api:app --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:10000 --timeout 120 --workers ${BOAT_RIDE_GUNICORN_WORKERS:-2}"
