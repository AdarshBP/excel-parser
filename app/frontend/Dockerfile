# Excel Parser — Frontend (Angular + nginx)
#
# Build context: app/frontend/
#   docker build -t excel-parser-frontend app/frontend/

# ── stage 1: build ──
FROM node:22-alpine AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . ./
RUN npx ng build --configuration production

# ── stage 2: serve with nginx ──
FROM nginx:alpine

# Remove default nginx site
RUN rm /etc/nginx/conf.d/default.conf

# Our config: serve SPA + proxy /api to backend
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Built Angular app
COPY --from=build /build/dist/frontend/browser /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
