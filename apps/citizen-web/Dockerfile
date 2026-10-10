# syntax=docker/dockerfile:1
# RAKSHA NET AI — citizen-web image.
# Built from the repository root so the shared workspace package is available:
#   docker build -f apps/citizen-web/Dockerfile .

FROM node:22-alpine AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY packages/api-client/package.json ./packages/api-client/
COPY packages/ui/package.json ./packages/ui/
COPY apps/citizen-web/package.json ./apps/citizen-web/
RUN npm ci --workspace @raksha/citizen-web --include-workspace-root

FROM node:22-alpine AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY packages ./packages
COPY apps/citizen-web ./apps/citizen-web
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace @raksha/citizen-web

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000

# Next's standalone output carries only the files the server actually needs.
COPY --from=builder /repo/apps/citizen-web/.next/standalone ./
COPY --from=builder /repo/apps/citizen-web/.next/static ./apps/citizen-web/.next/static

RUN addgroup -g 10001 -S raksha && adduser -u 10001 -S raksha -G raksha
USER raksha

EXPOSE 3000
CMD ["node", "apps/citizen-web/server.js"]
