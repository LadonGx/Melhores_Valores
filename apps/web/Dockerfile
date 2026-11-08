# Imagem de produção do front: build com pnpm e arquivos servidos pelo nginx.
# Build a partir da raiz do monorepo:  docker build -f apps/web/Dockerfile .
FROM node:20-alpine AS build
WORKDIR /repo
RUN npm install -g pnpm@9
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY packages/types/package.json packages/types/
COPY packages/utils/package.json packages/utils/
RUN pnpm install --frozen-lockfile
COPY packages packages
COPY apps/web apps/web
# Sem VITE_API_URL o front chama "/api", que o nginx repassa para a API
RUN pnpm --filter @mv/web exec vite build

FROM nginx:1.27-alpine
# API_UPSTREAM: endereço da API vista de dentro do container. NGINX_PORT: porta do nginx.
ENV API_UPSTREAM=http://api:8000 \
    NGINX_PORT=80
COPY apps/web/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /repo/apps/web/dist /usr/share/nginx/html
