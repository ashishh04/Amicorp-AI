# portal-web for the single-server deployment (deploy/README.md). Build context: ../frontend
#
# The same build as frontend/Dockerfile, with a larger Node heap. By default Node may use about a quarter of the
# server's memory, which on a 4 GB server is too little for the Angular build ("JavaScript heap out of memory").
# preflight.py makes sure memory and swap together can hold it.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npx -y npm@11 ci
COPY . .
ENV NODE_OPTIONS=--max-old-space-size=3072
RUN npx ng build --configuration production

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist/portal-web/browser /usr/share/nginx/html
# /assets/config.json is replaced by the file docker-compose.yml mounts.
EXPOSE 8080
USER 101
