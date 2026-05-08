# Demo Day frontend image (008-agent-frontend-v1).
#
# V1 packaging per specs/008-agent-frontend-v1/research.md §R1:
# Vite dev-server inside the container. Production-shape (multi-stage
# build serving a static bundle via nginx) is documented in research
# §R1 as the V1.1 upgrade recipe — not built here.

FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
