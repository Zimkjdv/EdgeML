FROM node:22-alpine AS build
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
ENV EDGEML_PROXY_MAX_BODY_SIZE=11m EDGEML_PROXY_SEND_TIMEOUT=300s EDGEML_PROXY_READ_TIMEOUT=300s
ENV NGINX_ENVSUBST_FILTER=^EDGEML_PROXY_
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

