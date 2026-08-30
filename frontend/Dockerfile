FROM node:22-alpine AS dependencies
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY frontend ./
ARG NEXT_PUBLIC_API_URL=""
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# rewrites() 는 next build 시점에 한 번 평가되어 routes-manifest.json 에
# 굳는다. 컨테이너 실행 시 environment: 로만 주면 이미 늦는다 — 반드시
# 빌드 인자로도 받아야 한다. 실제로 이걸 놓쳐서 프록시가 옛 기본값
# (127.0.0.1:8000, Node 서버 시절 포트)으로 굳어버린 적이 있다.
ARG API_PROXY_TARGET=http://backend:8787
ENV API_PROXY_TARGET=$API_PROXY_TARGET
# lint 실패로 배포가 막히지 않게 빌드만 한다. 린트는 개발 중에 돌린다.
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
