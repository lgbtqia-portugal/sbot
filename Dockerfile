FROM python:3-slim

ENV BOT_DIR=/opt/sbot
ENV CRONTAB="* * * * * units_cur > ${BOT_DIR}/logs/cron 2>&1"

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y cron units unicode git locales ripgrep \
	&& rm -rf /var/lib/apt/lists/* \
	&& localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
ENV LANG en_US.utf8

#RUN units_cur; exit 0

RUN useradd -Um sbot

#RUN echo "* * * * * units_cur > ${BOT_DIR}/logs/cron 2>&1" > /tmp/units_cur.cron
RUN echo "* * * * * units_cur > ${BOT_DIR}/logs/cron 2>&1" | crontab -u sbot -

USER sbot
# https://github.com/moby/buildkit/issues/2987
COPY --link --chown=1000:1000 . ${BOT_DIR}

WORKDIR ${BOT_DIR}

RUN pip install --user --no-warn-script-location -r requirements.txt

ENTRYPOINT ["python", "sbot"]
