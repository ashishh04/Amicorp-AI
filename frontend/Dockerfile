# Build: amc/portal-web (LLD, Runtime container). Pin base image digests in CI.
FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npx -y npm@11 ci
COPY . .
RUN npx ng build --configuration production

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist/portal-web/browser /usr/share/nginx/html
# /assets/config.json is replaced by the ConfigMap mount in each environment.
EXPOSE 8080
USER 101
