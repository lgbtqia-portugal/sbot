from datetime import datetime
import sys

logfile = open('sbot.log', 'a', encoding='utf-8')
stdout = sys.stdout.isatty()

def write(text):
	line = '%s %s' % (datetime.now(), text)
	if 0 <= line.rfind('\n') < len(line)-1:
		line += '\n\n'
	else:
		line += '\n'

	if stdout:
		print(line, end='')
	logfile.write(line)

def flush():
	logfile.flush()

def close():
	logfile.close()
