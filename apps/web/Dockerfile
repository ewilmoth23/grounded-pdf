# syntax=docker/dockerfile:1
FROM node:26-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
ENV NGINX_ENTRYPOINT_QUIET_LOGS=1
ARG MAX_UPLOAD_BATCH_MB=200
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN case "$MAX_UPLOAD_BATCH_MB" in \
      ''|*[!0-9]*) echo "MAX_UPLOAD_BATCH_MB must be a positive integer" >&2; exit 1 ;; \
    esac \
    && test "$MAX_UPLOAD_BATCH_MB" -gt 0 \
    && proxy_limit_mb=$((MAX_UPLOAD_BATCH_MB + 1)) \
    && sed -i "s/__MAX_UPLOAD_BATCH_MB__/${proxy_limit_mb}/" /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=5s --start-period=5s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
