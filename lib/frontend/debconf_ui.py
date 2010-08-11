# -*- coding: UTF-8 -*-

# Copyright (C) 2008, 2009 Canonical Ltd.
# Written by Colin Watson <cjwatson@ubuntu.com>.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

# This is a simple frontend that does not perform any filtering; instead, it
# just runs everything using the usual debconf frontend. This is suitable
# for use on a server.
#
# Note that this frontend relies on being run under the control of a debconf
# frontend; the main oem-config program takes care of this.

import sys
import os
import textwrap

from debconf import Debconf

from oem_config.components import console_setup, language, timezone, user, \
                                  network, tasks, \
                                  language_apply, timezone_apply, \
                                  console_setup_apply
from oem_config.frontend.base import BaseFrontend

class Frontend(BaseFrontend):
    def __init__(self):
        BaseFrontend.__init__(self)

        self.db.info('oem-config/text/oem_config')

        self.previous_excepthook = sys.excepthook
        sys.excepthook = self.excepthook

        # Set default language.
        dbfilter = language.Language(self, self.db)
        dbfilter.cleanup()

    def excepthook(self, exctype, excvalue, exctb):
        """Crash handler."""

        if (issubclass(exctype, KeyboardInterrupt) or
            issubclass(exctype, SystemExit)):
            return

        self.post_mortem(exctype, excvalue, exctb)

        self.previous_excepthook(exctype, excvalue, exctb)

    def run(self):
        if os.getuid() != 0:
            print >>sys.stderr, textwrap.fill(
                'This program must be run with administrative privileges, and '
                'cannot continue without them.')
            sys.exit(1)

        self.current_page = 0

        while self.current_page >= 0 and self.current_page < len(self.pages):
            current_name = self.pages[self.current_page]
            if current_name == 'step_language':
                self.db.settitle('oem-config/text/language_heading_label')
                step = language.Language(self, self.db)
            elif current_name == 'step_timezone':
                self.db.settitle('oem-config/text/timezone_heading_label')
                step = timezone.Timezone(self, self.db)
            elif current_name == 'step_keyboard':
                self.db.settitle('oem-config/text/keyboard_heading_label')
                step = console_setup.ConsoleSetup(self, self.db)
            elif current_name == 'step_user':
                self.db.settitle('oem-config/text/user_heading_label')
                step = user.User(self, self.db)
            elif current_name == 'step_network':
                self.db.settitle('oem-config/text/network_heading_label')
                step = network.Network(self, self.db)
            elif current_name == 'step_tasks':
                self.db.settitle('oem-config/text/tasks_heading_label')
                step = tasks.Tasks(self, self.db)
            else:
                raise ValueError, "step %s not recognised" % current_name

            ret = step.run_unfiltered()

            if ret == 10:
                self.current_page -= 1
            else:
                self.current_page += 1

        # TODO: handle errors
        if self.current_page >= len(self.pages):
            self.db.progress('START', 0, 3, 'oem-config/text/applying')

            step = language_apply.LanguageApply(self, self.db)
            step.run_unfiltered()
            self.db.progress('STEP', 1)

            step = timezone_apply.TimezoneApply(self, self.db)
            step.run_unfiltered()
            self.db.progress('STEP', 1)

            step = console_setup_apply.ConsoleSetupApply(self, self.db)
            step.run_unfiltered()
            self.db.progress('STEP', 1)

            self.db.progress('STOP')

            return 0
        else:
            return 10

    def stop(self):
        self.db.stop()
