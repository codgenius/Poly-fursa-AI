FROM node:20-alpine

# Accept build-time argument for agent URL (passed by GitHub Actions or docker-compose)
ARG NEXT_PUBLIC_AGENT_URL=/agent-api
ENV NEXT_PUBLIC_AGENT_URL=${NEXT_PUBLIC_AGENT_URL}

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "-H", "0.0.0.0", "-p", "3000"]
