# syntax=docker/dockerfile:1
# RAKSHA NET AI — responder-web image.
# Built from the repository root so the shared workspace package is available:
#   docker build -f apps/responder-web/Dockerfile .

FROM node:22-alpine AS deps
WORKDIR /repo
COPY package.json package-lock.json ./
COPY packages/api-client/package.json ./packages/api-client/
COPY apps/responder-web/package.json ./apps/responder-web/
RUN npm ci --workspace @raksha/responder-web --include-workspace-root

FROM node:22-alpine AS builder
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY packages ./packages
COPY apps/responder-web ./apps/responder-web
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build --workspace @raksha/responder-web

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3002

# Next's standalone output carries only the files the server actually needs.
COPY --from=builder /repo/apps/responder-web/.next/standalone ./
COPY --from=builder /repo/apps/responder-web/.next/static ./apps/responder-web/.next/static

RUN addgroup -g 10001 -S raksha && adduser -u 10001 -S raksha -G raksha
USER raksha

EXPOSE 3002
CMD ["node", "apps/responder-web/server.js"]
