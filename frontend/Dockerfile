FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --no-audit --no-fund

COPY . .

EXPOSE 5173

# Dev server includes the /api + WebSocket proxy to the backend service.
CMD ["npm", "run", "dev", "--", "--host"]
