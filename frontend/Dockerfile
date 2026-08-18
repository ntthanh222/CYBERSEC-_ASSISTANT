# syntax=docker/dockerfile:1
# Builder stage: compile the real Vite/React app (frontend/src) to static
# assets. The previous version of this Dockerfile predated the Phase 2/2.6
# React migration and copied the repo-root index.html/assets/ directly -
# those are the dev-mode template (loads unbuilt /src/main.tsx, which nginx
# cannot serve) and the leftover Phase 1 static dashboard, respectively.
# That shipped a blank, non-functional page in every prior Docker build -
# see PHASE_2_7A_RELEASE_HARDENING_REPORT.md for how this was found.
FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig*.json vite.config.ts postcss.config.js tailwind.config.js index.html ./
COPY public/ ./public/
COPY src/ ./src/
# VITE_-prefixed variables are compiled into the bundle at this build step
# (Vite's own convention, read from a .env file in the build context) -
# never a runtime env var, since there is no server-side process here to
# read one from. Only the publishable Supabase key belongs in this file -
# see frontend/.env.example.
COPY .env* ./
RUN npm run build

# nginx-unprivileged runs as a non-root user (uid 101) on an unprivileged
# port (8080) out of the box — the plain nginx image runs its master
# process as root, which Trivy flags (DS-0002 "Image user should not be
# 'root'").
FROM nginxinc/nginx-unprivileged:1.27-alpine

# The base image tag is pinned and its Alpine packages go stale between
# nginx point releases; pull current patches from the same Alpine branch
# at build time (Trivy image scan: fixed several HIGH/CRITICAL OS CVEs in
# libssl3/libcrypto3/libxml2/etc this way). Requires root momentarily —
# the base image otherwise runs as USER nginx (uid 101) by default.
USER root
RUN apk upgrade --no-cache
USER nginx

RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist/index.html /usr/share/nginx/html/index.html
COPY --from=builder /app/dist/static/ /usr/share/nginx/html/static/

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --retries=10 --start-period=10s \
    CMD wget -qO- http://127.0.0.1:8080/health || exit 1
