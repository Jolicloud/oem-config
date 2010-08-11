# apport hook for oem-config; adds log file

import os.path

def add_info(report):
    if os.path.exists('/var/log/oem-config.log'):
        report['OemConfigLog'] = ('/var/log/oem-config.log',)
