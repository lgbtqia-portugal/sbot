FROM python:3-slim

ENV BOT_DIR=/opt/sbot

RUN apt-get update && apt-get install -y units unicode git locales ripgrep \
	&& rm -rf /var/lib/apt/lists/* \
	&& localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
ENV LANG en_US.utf8

RUN useradd -Um sbot

USER sbot

COPY --link --chown=sbot:sbot . ${BOT_DIR}

WORKDIR ${BOT_DIR}

RUN pip install --user --no-warn-script-location -r requirements.txt

ENTRYPOINT ["python", "sbot"]
