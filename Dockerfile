FROM python:3.10-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy source
COPY src/ src/
COPY trips/ trips/
RUN pip install --no-cache-dir -e .

# Pre-download coastline shapefile into the image so first request isn't slow
RUN python -c "from boat_ride.geo.shoreline import ShorelineData; ShorelineData.get().coastline; print('Coastline cached')"

EXPOSE 10000

CMD ["uvicorn", "boat_ride.api:app", "--host", "0.0.0.0", "--port", "10000"]
