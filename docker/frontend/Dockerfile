FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# "npm ci" installs exactly what the lockfile records and fails if the two
# have drifted; "npm install" silently resolved fresh versions on every image
# build, and the lockfile was not even in the repository to compare against.
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.31-alpine
COPY --from=build /app/dist /opt/new_dist
COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN echo -e '#!/bin/sh\nrm -rf /usr/share/nginx/html/*\ncp -R /opt/new_dist/* /usr/share/nginx/html/\nexec "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh
EXPOSE 3333
ENTRYPOINT ["/entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
