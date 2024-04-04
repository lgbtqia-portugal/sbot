import canned
import management
import timer
import utils

commands = {
    'help': utils.help,
    'botinfo': utils.botinfo,
    'ping': utils.ping,
    'calc': utils.calc,
    'roll': utils.roll,
    'timer': timer.timer,
    'units': utils.units,
    'unicode': utils.unicode,
    'time': utils.time,
    'weather': utils.weather,

    # management commands
    'can': canned.canned,
    'listbots': management.listbots,
    'verify': management.verify,
    'massban': management.mass_ban,
    'cleanup': management.cleanup,

    #'join': management.join,
    #'leave': management.leave,
    #'roles': management.list_roles,
    #'groups': management.list_roles,


}
