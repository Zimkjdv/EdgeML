FROM node:22-alpine AS build
WORKDIR /app
ARG VITE_EDGEML_API_TOKEN=""
ENV VITE_EDGEML_API_TOKEN=$VITE_EDGEML_API_TOKEN
COPY package.json .
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80

