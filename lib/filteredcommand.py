# -*- coding: UTF-8 -*-

# Copyright (C) 2005, 2006 Canonical Ltd.
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

import sys
import os
import re
import signal
import subprocess

import debconf
from debconf import Debconf, DebconfCommunicator

from debconffilter import DebconfFilter

# We identify as this to debconf.
PACKAGE = 'oem-config'

# Bitfield constants for process_input and process_output.
DEBCONF_IO_IN = 1
DEBCONF_IO_OUT = 2
DEBCONF_IO_ERR = 4
DEBCONF_IO_HUP = 8

class FilteredCommand(object):
    def __init__(self, frontend, db=None):
        self.frontend = frontend
        # db does not normally need to be specified.
        self.db = db
        self.done = False
        self.current_question = None
        self.succeeded = False

    @classmethod
    def debug(self, fmt, *args):
        if 'OEM_CONFIG_DEBUG' in os.environ:
            message = fmt % args
            print >>sys.stderr, '%s: %s' % (PACKAGE, message)
            sys.stderr.flush()

    def start(self, auto_process=False):
        self.status = None
        self.db = DebconfCommunicator(PACKAGE, cloexec=True)
        prep = self.prepare()
        self.command = prep[0]
        question_patterns = prep[1]
        if len(prep) > 2:
            env = prep[2]
        else:
            env = {}

        self.ui_loop_level = 0

        self.debug("Starting up '%s' for %s.%s", self.command,
                   self.__class__.__module__, self.__class__.__name__)
        self.debug("Watching for question patterns %s",
                   ', '.join(question_patterns))

        widgets = {}
        for pattern in question_patterns:
            widgets[pattern] = self
        self.dbfilter = DebconfFilter(self.db, widgets)

        # TODO: Set as unseen all questions that we're going to ask.

        self.dbfilter.start(self.command, blocking=False, extra_env=env)
        # Clearly, this isn't enough for full non-blocking operation.
        # However, debconf itself is generally quick, and the confmodule
        # will generally be listening for a reply when we try to send one;
        # the slow bit is waiting for the confmodule to decide to send a
        # command. Therefore, this is the only file descriptor we bother to
        # watch, which greatly simplifies our life.
        self.frontend.watch_debconf_fd(
            self.dbfilter.subout_fd, self.process_input)

    def process_line(self):
        return self.dbfilter.process_line()

    def wait(self):
        ret = self.dbfilter.wait()

        if ret != 0:
            # TODO: error message if ret != 10
            self.debug("%s exited with code %d", self.command, ret)

        self.cleanup()

        self.db.shutdown()

        return ret

    def cleanup(self):
        pass

    def run_command(self, auto_process=False):
        self.start(auto_process=auto_process)
        if auto_process:
            self.enter_ui_loop()
        else:
            while self.process_line():
                pass
            self.status = self.wait()
        return self.status

    def run_unfiltered(self):
        """This may only be called under the control of a debconf frontend."""

        self.status = None

        prep = self.prepare(unfiltered=True)
        self.command = prep[0]
        if len(prep) > 2:
            env = prep[2]
        else:
            env = {}

        self.debug("Starting up '%s' unfiltered for %s.%s", self.command,
                   self.__class__.__module__, self.__class__.__name__)

        def subprocess_setup():
            os.environ['HOME'] = '/root'
            os.environ['LC_COLLATE'] = 'C'
            for key, value in env.iteritems():
                os.environ[key] = value
            # Python installs a SIGPIPE handler by default. This is bad for
            # non-Python subprocesses, which need SIGPIPE set to the default
            # action.
            signal.signal(signal.SIGPIPE, signal.SIG_DFL)

        ret = subprocess.call(self.command, preexec_fn=subprocess_setup)
        if ret != 0:
            # TODO: error message if ret != 10
            self.debug("%s exited with code %d", self.command, ret)

        self.cleanup()

        return ret

    def process_input(self, source, condition):
        if source != self.dbfilter.subout_fd:
            return True

        call_again = True

        if condition & DEBCONF_IO_IN:
            if not self.process_line():
                call_again = False

        if (condition & DEBCONF_IO_ERR) or (condition & DEBCONF_IO_HUP):
            call_again = False

        if not call_again:
            # TODO cjwatson 2006-02-08: We hope this happens quickly! It
            # would be better to do this out-of-band somehow.
            self.status = self.wait()
            self.exit_ui_loops()
            self.frontend.debconffilter_done(self)

        return call_again

    # Split a string on commas, stripping surrounding whitespace, and
    # honouring backslash-quoting.
    def split_choices(self, text):
        textlen = len(text)
        index = 0
        items = []
        item = ''

        while index < textlen:
            if text[index] == '\\' and index + 1 < textlen:
                if text[index + 1] == ',' or text[index + 1] == ' ':
                    item += text[index + 1]
                    index += 1
            elif text[index] == ',':
                items.append(item.strip())
                item = ''
            else:
                item += text[index]
            index += 1

        if item != '':
            items.append(item.strip())

        return items

    def choices_untranslated(self, question):
        choices = unicode(self.db.metaget(question, 'choices-c'), 'utf-8')
        return self.split_choices(choices)

    def choices(self, question):
        choices = unicode(self.db.metaget(question, 'choices'), 'utf-8')
        return self.split_choices(choices)

    def choices_display_map(self, question):
        """Returns a mapping from displayed (translated) choices to
        database (untranslated) choices.  It can be used both ways,
        since both choices and the untranslated choices are sequences
        without duplication.
        """

        _map = {}
        choices = self.choices(question)
        choices_c = self.choices_untranslated(question)
        for i in range(len(choices)):
            _map[choices[i]] = choices_c[i]
        return _map

    def description(self, question):
        return unicode(self.db.metaget(question, 'description'), 'utf-8')

    def extended_description(self, question):
        return unicode(self.db.metaget(question, 'extended_description'),
                       'utf-8')

    def translate_title(self, question):
        # TODO cjwatson 2006-07-06: broken, needs to be done in frontend
        widget = self.glade.get_widget('dialog')
        widget.set_title(self.description(question))

    def translate_labels(self, questions):
        # TODO cjwatson 2006-07-06: broken, needs to be done in frontend
        for label, question in questions.items():
            widget = self.glade.get_widget(label)
            widget.set_label(self.description(question))

    def translate_to_c(self, question, value):
        choices = self.choices(question)
        choices_c = self.choices_untranslated(question)
        for i in range(len(choices)):
            if choices[i] == value:
                return choices_c[i]
        raise ValueError, value

    def value_index(self, question):
        value = self.db.get(question)
        choices_c = self.choices_untranslated(question)
        for i in range(len(choices_c)):
            if choices_c[i] == value:
                return i
        raise ValueError, value

    def escape(self, text):
        escaped = text.replace('\\', '\\\\').replace('\n', '\\n')
        return re.sub(r'(\s)', r'\\\1', escaped)

    def preseed(self, name, value, seen=True, escape=False):
        if escape:
            value = self.escape(value)
        value = value.encode("UTF-8", "ignore")
        if escape:
            self.db.capb('escape')
        try:
            self.db.set(name, value)
        except debconf.DebconfError:
            self.db.register('debian-installer/dummy', name)
            self.db.set(name, value)
            self.db.subst(name, 'ID', name)
        if escape:
            self.db.capb('')

        if seen:
            self.db.fset(name, 'seen', 'true')

    def preseed_bool(self, name, value, seen=True):
        if value:
            self.preseed(name, 'true', seen)
        else:
            self.preseed(name, 'false', seen)

    def preseed_as_c(self, name, value, seen=True):
        self.preseed(name, self.translate_to_c(name, value), seen)

    # Cause the frontend to enter a recursive main loop. Will block until
    # something causes the frontend to exit that loop (probably by calling
    # exit_ui_loops).
    def enter_ui_loop(self):
        self.ui_loop_level += 1
        self.frontend.run_main_loop()

    # Exit any recursive main loops we caused the frontend to enter.
    def exit_ui_loops(self):
        while self.ui_loop_level > 0:
            self.ui_loop_level -= 1
            self.frontend.quit_main_loop()

    # User selected OK, Forward, or similar. Subclasses should override this
    # to send user-entered information back to debconf (perhaps using
    # preseed()) and return control to the filtered command. After this
    # point, self.done is set so no further user interaction should take
    # place unless an error resets it.
    def ok_handler(self):
        self.succeeded = True
        self.done = True
        self.exit_ui_loops()

    # User selected Cancel, Back, or similar. Subclasses should override
    # this to send user-entered information back to debconf (perhaps using
    # preseed()) and return control to the filtered command. After this
    # point, self.done is set so no further user interaction should take
    # place unless an error resets it.
    def cancel_handler(self):
        self.succeeded = False
        self.done = True
        self.exit_ui_loops()

    def error(self, priority, question):
        self.succeeded = False
        self.done = False
        return True

    def run(self, priority, question):
        self.current_question = question
        if not self.done:
            self.succeeded = False
            self.enter_ui_loop()
        return self.succeeded
