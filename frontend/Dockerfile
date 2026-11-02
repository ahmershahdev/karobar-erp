# Build from the repository root: docker build -f frontend/Dockerfile .
FROM node:26.13.0-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ .
ARG VITE_SITE_URL
ARG VITE_API_BASE_URL=
ENV VITE_SITE_URL=${VITE_SITE_URL} VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM nginx:1.31.8-alpine
COPY deploy/nginx/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx/site.conf /etc/nginx/conf.d/default.conf
COPY deploy/nginx/snippets /etc/nginx/snippets
COPY --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
