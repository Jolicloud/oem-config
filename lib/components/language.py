# -*- coding: UTF-8 -*-

# Copyright (C) 2005 Canonical Ltd.
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

import os
import re
import locale
import subprocess

from oem_config.filteredcommand import FilteredCommand
from oem_config import i18n
from oem_config import im_switch
from oem_config import osextras

class Language(FilteredCommand):
    def prepare(self, unfiltered=False):
        self.language_question = None
        self.initial_language = None
        self.db.fset('localechooser/languagelist', 'seen', 'false')
        try:
            os.unlink('/var/lib/localechooser/preseeded')
            os.unlink('/var/lib/localechooser/langlevel')
        except OSError:
            pass
        questions = ['localechooser/languagelist']
        return (['/usr/lib/oem-config/language/localechooser-wrapper'],
                questions)

    def run(self, priority, question):
        if question == 'localechooser/languagelist':
            self.language_question = question
            if self.initial_language is None:
                self.initial_language = self.db.get(question)
            current_language_index = self.value_index(question)
            current_language = "English"

            import gzip
            languagelist = gzip.open('/usr/lib/oem-config/language/languagelist.data.gz')
            language_display_map = {}
            i = 0
            for line in languagelist:
                line = unicode(line, 'utf-8')
                if line == '' or line == '\n':
                    continue
                code, name, trans = line.strip(u'\n').split(u':')[1:]
                if code in ('dz', 'km'):
                    i += 1
                    continue
                language_display_map[trans] = (name, code)
                if i == current_language_index:
                    current_language = trans
                i += 1
            languagelist.close()

            def compare_choice(x, y):
                result = cmp(language_display_map[x][1],
                             language_display_map[y][1])
                if result != 0:
                    return result
                return cmp(x, y)

            sorted_choices = sorted(language_display_map, compare_choice)
            self.frontend.set_language_choices(sorted_choices,
                                               language_display_map)
            self.frontend.set_language(current_language)

        return FilteredCommand.run(self, priority, question)

    def ok_handler(self):
        if self.language_question is not None:
            new_language = self.frontend.get_language()
            self.preseed(self.language_question, new_language)
            if (self.initial_language is None or
                self.initial_language != new_language):
                self.db.reset('debian-installer/country')
        FilteredCommand.ok_handler(self)

    def cleanup(self):
        di_locale = self.db.get('debian-installer/locale')
        if di_locale not in i18n.get_supported_locales():
            di_locale = self.db.get('debian-installer/fallbacklocale')
        if di_locale == '':
            # TODO cjwatson 2006-07-17: maybe fetch
            # languagechooser/language-name and set a language based on
            # that?
            di_locale = 'en_US.UTF-8'
        if di_locale != self.frontend.locale:
            self.frontend.locale = di_locale
            os.environ['LANG'] = di_locale
            os.environ['LANGUAGE'] = di_locale
            try:
                locale.setlocale(locale.LC_ALL, '')
            except locale.Error, e:
                self.debug('locale.setlocale failed: %s (LANG=%s)',
                           e, di_locale)
            if osextras.find_on_path('fontconfig-voodoo'):
                subprocess.call(['fontconfig-voodoo',
                                 '--auto', '--force', '--quiet'])
            im_switch.start_im()
