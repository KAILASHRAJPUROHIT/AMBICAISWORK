FROM node:20-slim

ENV NODE_ENV=production \
    PUPPETEER_SKIP_DOWNLOAD=true \
    PORT=8080

WORKDIR /app
COPY package.json package-lock.json* .npmrc* ./
RUN npm install --omit=dev
COPY . .

RUN useradd --system --create-home --uid 10002 aradhana \
    && mkdir -p /app/data /app/logs \
    && chown -R aradhana:aradhana /app
USER aradhana

EXPOSE 8080
CMD ["node", "src/index.js", "--no-whatsapp"]
