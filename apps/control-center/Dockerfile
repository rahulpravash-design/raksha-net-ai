# syntax=docker/dockerfile:1
# RAKSHA NET AI — control-center image.
# Built from the repository root so the shared workspace package is available:
#   docker build -f apps/control-center/Dockerfile .

FROM node:22-alpine AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY packages/api-client/package.json ./packages/api-client/
COPY apps/control-center/package.json ./apps/control-center/
RUN npm ci --workspace @raksha/control-center --include-workspace-root

FROM node:22-alpine AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY packages ./packages
COPY apps/control-center ./apps/control-center
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace @raksha/control-center

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3001

# Next's standalone output carries only the files the server actually needs.
COPY --from=builder /repo/apps/control-center/.next/standalone ./
COPY --from=builder /repo/apps/control-center/.next/static ./apps/control-center/.next/static

RUN addgroup -g 10001 -S raksha && adduser -u 10001 -S raksha -G raksha
USER raksha

EXPOSE 3001
CMD ["node", "apps/control-center/server.js"]
