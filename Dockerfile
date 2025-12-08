FROM python:3.11-slim

WORKDIR /app

# Install curl and Node.js for frontend build
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    node --version && npm --version && \
    rm -rf /var/lib/apt/lists/*

# Install system dependencies for Playwright
# Fix for missing/replaced font packages in Debian Trixie
RUN apt-get update && apt-get install -y \
    fonts-unifont \
    fonts-liberation \
    fonts-noto-color-emoji \
    libnss3 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    libxss1 \
    libasound2 \
    libxshmfence1 \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy package files and install frontend dependencies
COPY package*.json ./
RUN npm install

# Copy frontend source files
COPY index.html ./
COPY vite.config.js ./
COPY src/ ./src/

# Build frontend
RUN npm run build

# Copy Python requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (without --with-deps since we installed deps manually)
# This avoids the font package conflicts in Debian Trixie
RUN playwright install chromium

# Copy application code
COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
