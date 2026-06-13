# =========================================================
# Stage 1: Build the React Frontend
# =========================================================
FROM node:20-slim AS builder
WORKDIR /app

# Install and cache dependencies
COPY package*.json ./
RUN npm install

# Copy configuration and source directories
COPY index.html tsconfig.json vite.config.ts ./
COPY src/ ./src/
COPY assets/ ./assets/

# Build the frontend to /app/dist
RUN npm run build

# =========================================================
# Stage 2: Modern Python Server with Prebuilt Playwright & Chrome
# =========================================================
# Use the official Microsoft Playwright Python base image
# This pre-installs Python, Playwright 1.44.0, node, and all browser binaries + OS dependencies perfectly!
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy AS runner
WORKDIR /app

# Install Python application dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy React static distribution from building container
COPY --from=builder /app/dist ./dist

# Copy Python backend server file
COPY server.py ./

# Create uploads storage structure with read-write permissions
RUN mkdir -p uploads && chmod 777 uploads

# Define default runtime environment variables
ENV PORT=3000
# Playwright runs nicely as root in docker with this setup, and uses pre-installed browser binaries
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Expose server port
EXPOSE 3000

# Execute server boot sequence
CMD ["python", "server.py"]
