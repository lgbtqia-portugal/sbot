# sbot

a discord bot

## setup

set up an app at https://discord.com/developers/applications with the `bot` scope
```
pip3 install -r requirements.txt
mkdir config
cp config.yaml.example config/config.yaml
$EDITOR config/config.yaml
./sbot
```

## Docker

Build:
```shell
docker build -t lgbtqia-portugal/sbot:$(git rev-parse --short HEAD) .
docker tag lgbtqia-portugal/sbot:$(git rev-parse --short HEAD) lgbtqia-portugal/sbot:latest
```

Run:
```shell
docker run -d --name sbot -v /somedir/sbot/config:/opt/sbot/config --restart=always -m 1G lgbtqia-portugal/sbot:latest
```
