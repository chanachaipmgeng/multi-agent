FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
# Bake Grafana host port into SPA (7920 often uses 3030 when :3000 is taken).
ARG VITE_GRAFANA_PORT=3000
ARG VITE_HERMES_PORT=9119
ENV VITE_GRAFANA_PORT=$VITE_GRAFANA_PORT
ENV VITE_HERMES_PORT=$VITE_HERMES_PORT
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
