# Stage 1: Development with Vite dev server
FROM node:22-alpine AS dev

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Stage 2: Build static assets
FROM dev AS build

ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# Stage 3: Serve with Nginx (production default)
FROM nginx:alpine AS prod

ENV PORT=80 \
    BACKEND_URL=http://backend:8000 \
    NGINX_ENVSUBST_FILTER="PORT|BACKEND_URL"

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
