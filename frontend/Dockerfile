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

RUN npm run build

# Stage 3: Serve with Nginx (production default)
FROM nginx:alpine AS prod

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

