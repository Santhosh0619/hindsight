# ── Base ──────────────────────────────────────────────────────────────────────
FROM node:20-slim AS base
WORKDIR /app
ENV NODE_ENV=development

# ── Dependencies ──────────────────────────────────────────────────────────────
FROM base AS deps
COPY package.json package-lock.json ./
RUN npm ci

# ── Development (Vite dev server with HMR) ────────────────────────────────────
FROM deps AS development
COPY . .
EXPOSE 5173

# ── Build ─────────────────────────────────────────────────────────────────────
FROM deps AS builder
ENV NODE_ENV=production
COPY . .
RUN npm run build

# ── Production (nginx) ────────────────────────────────────────────────────────
FROM nginx:alpine AS production
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s \
    CMD curl -f http://localhost/ || exit 1
