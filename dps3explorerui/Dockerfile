# syntax=docker/dockerfile:1.7

# ---------- deps ----------
FROM public.ecr.aws/bitnami/node:20.11.0-debian-11-r15 AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# ---------- builder ----------
FROM public.ecr.aws/bitnami/node:20.11.0-debian-11-r15 AS builder
WORKDIR /app
ARG NEXT_PUBLIC_HOSTNAME
ENV NEXT_PUBLIC_HOSTNAME=$NEXT_PUBLIC_HOSTNAME
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ---------- runner ----------
FROM public.ecr.aws/bitnami/node:20.11.0-debian-11-r15 AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=80
ENV HOSTNAME=0.0.0.0

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/.next/server ./server

# Required to bind to privileged port 80 (Bitnami image otherwise runs as UID 1001).
USER 0

EXPOSE 80
CMD ["node", "server.js"]
