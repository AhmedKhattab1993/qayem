FROM node:22.23.2-bookworm-slim AS pi
RUN npm install --global @earendil-works/pi-coding-agent@0.84.3

FROM python:3.13-slim-bookworm
COPY --from=pi /usr/local/bin/node /usr/local/bin/node
COPY --from=pi /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js /usr/local/bin/pi
WORKDIR /app
COPY cloudflare/updater/container/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --no-cache-dir --no-deps .
COPY cloudflare/updater/container/models.json /app/pi-models.json
RUN mkdir -p /data /root/.pi/agent
ENV QAYEM_DB=/data/qayem.db PYTHONUNBUFFERED=1 COLUMNS=140 TERM=dumb
EXPOSE 8080
CMD ["python", "-m", "qayem.cloud_pipeline"]
