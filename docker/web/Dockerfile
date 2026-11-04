# syntax=docker/dockerfile:1
FROM node:22-alpine AS dependencies

WORKDIR /var/www/html

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

FROM dependencies AS builder

ENV NEXT_TELEMETRY_DISABLED=1

COPY . .
RUN npm run build

FROM node:22-alpine AS runner

LABEL org.opencontainers.image.title="WMS SaaS Web" \
      org.opencontainers.image.source="https://github.com/GabrielLourenco1912/wms-saas-web"

WORKDIR /var/www/html

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

RUN addgroup --system --gid 1001 nextjs \
    && adduser --system --uid 1001 --ingroup nextjs nextjs \
    && chown nextjs:nextjs /var/www/html

COPY --from=builder --chown=1001:1001 /var/www/html/.next/standalone ./
COPY --from=builder --chown=1001:1001 /var/www/html/.next/static ./.next/static
COPY --from=builder --chown=1001:1001 /var/www/html/public ./public

USER 1001:1001
EXPOSE 3000

CMD ["node", "server.js"]
