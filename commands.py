import canned
import management
import timer
import utils

commands = {
    'help': utils.help,
    'botinfo': utils.botinfo,
    'ping': utils.ping,
    'calc': utils.calc,
    'unicode': utils.unicode,
    'units': utils.units,
    'roll': utils.roll,
    'time': utils.time,
    'weather': utils.weather,

    'timer': timer.timer,

    'listbots': utils.listbots,

    #'join': management.join,
    #'leave': management.leave,
    #'roles': management.list_roles,
    #'groups': management.list_roles,
    #'cleanup': management.cleanup,
    #'massban': management.mass_ban,

    #'can': canned.canned,
}
