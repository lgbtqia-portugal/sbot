FROM python:3-slim

ENV BOT_DIR=/opt/sbot

RUN apt-get update && apt-get install -y units unicode git locales ripgrep \
	&& rm -rf /var/lib/apt/lists/* \
	&& localedef -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8
ENV LANG en_US.utf8

RUN useradd -Um sbot

RUN git clone --depth=1 "https://github.com/lgbtqia-portugal/sbot.git" --single-branch --branch main ${BOT_DIR}

WORKDIR ${BOT_DIR}

RUN chown -R sbot ${BOT_DIR}

USER sbot

RUN pip install --user --no-warn-script-location -r requirements.txt

ENTRYPOINT ["python", "sbot"]
