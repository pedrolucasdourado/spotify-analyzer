FROM node:22-alpine AS build
WORKDIR /app
COPY web/package.json ./package.json
RUN npm install --no-fund --no-audit
COPY web/ ./
RUN npm run build

FROM nginx:alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
