import os
import json
import logging
import logging.handlers
from subprocess import CalledProcessError, run
from natsort import natsorted

import config
import log

log_file = config.bot.user_audit_log['file']
log_dir = config.bot.user_audit_log['dir']

def setup():
    try:
        log.write(f'creating user audit log directory at "{log_dir}"')
        os.mkdir(log_dir, mode=0o770)
    except FileExistsError:
        log.write('user audit log directory already exists')

    log_handler = logging.handlers.RotatingFileHandler(os.path.join(log_dir, log_file), \
        backupCount=10, maxBytes=10*1000*1000)
    logger = logging.getLogger()
    logger.addHandler(log_handler)
    logger.setLevel(logging.INFO)

    log.write("found log files:")
    for file in natsorted(os.listdir(log_dir)):
        log.write(os.path.join(log_dir, file))

def search(msg):
    output = []
    log.write("Searching Log Files:")
    for file in natsorted(os.listdir(log_dir)):
        log.write(file)
        if file.startswith(log_file):
            command = [
                'rg',
                '-N',
                '--no-stats',
                '--color=never',
                f'"id": "{msg}"',
                os.path.join(log_dir, file),
            ]
            try:
                result = run(command, check=True, text=True, capture_output=True)
                output += reversed(result.stdout.splitlines())
            except CalledProcessError as e:
                if e.returncode != 1:
                    raise CalledProcessError from e

        if len(output) > 1:
            return [json.loads(i) for i in output]
    return None
