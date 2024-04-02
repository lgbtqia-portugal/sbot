import json
import logging
import logging.handlers
from subprocess import run, CalledProcessError

import config

log_file = config.bot.user_audit_log['file']

def setup():
    log_handler = logging.handlers.RotatingFileHandler(log_file, \
        backupCount=1, maxBytes=100*1000*1000)
    logger = logging.getLogger()
    logger.addHandler(log_handler)
    logger.setLevel(logging.INFO)

def search(msg):
    command = [
        'rg',
        '-N',
        '--no-stats',
        '--color=never',
        f'{msg}',
        log_file,
    ]
    try:
        result = run(command, check=True, text=True, capture_output=True)
        return [json.loads(i) for i in result.stdout.splitlines()]
    except CalledProcessError:
        return
