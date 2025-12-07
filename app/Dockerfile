FROM node:24

WORKDIR /app

RUN npm install -g wrangler

# Copy package.json and install dependencies
COPY package*.json ./
RUN npm install

# Copy source code
COPY . .

# wrangler reads variables only `.dev.vars`, not from ENV nor `.env` as docs say
CMD ["bash", "-c", "env > .dev.vars && npx wrangler dev --ip 0.0.0.0 --port 8787"]
