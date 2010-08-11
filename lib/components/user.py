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

from oem_config.filteredcommand import FilteredCommand

# TODO: skip this if there's already a user configured, or re-ask and create
# a new one, or what?
class User(FilteredCommand):
    def prepare(self, unfiltered=False):
        # We intentionally don't listen to passwd/auto-login or
        # user-setup/encrypt-home because we don't want those alone to force
        # the page to be shown, if they're the only questions not preseeded.
        questions = ['^passwd/user-fullname$', '^passwd/username$',
                     '^passwd/user-password$', '^passwd/user-password-again$',
                     '^user-setup/password-weak$',
                     'ERROR']
        return (['/usr/lib/oem-config/user/user-setup-wrapper', '/'],
                questions)

    def set(self, question, value):
        if question == 'passwd/username':
            if self.frontend.get_username() != '':
                self.frontend.set_username(value)

    def run(self, priority, question):
        if question.startswith('user-setup/password-weak'):
            # A dialog is a bit clunky, but workable for now. Perhaps it
            # would be better to display some text in the style of
            # password_error, and then let the user carry on anyway by
            # clicking next again?
            response = self.frontend.question_dialog(
                self.description(question),
                self.extended_description(question),
                ('oem-config/text/go_back', 'oem-config/text/continue'))
            if response is None or response == 'oem-config/text/continue':
                self.preseed(question, 'true')
            else:
                self.preseed(question, 'false')
            return True

        return FilteredCommand.run(self, priority, question)

    def ok_handler(self):
        fullname = self.frontend.get_fullname()
        username = self.frontend.get_username()
        password = self.frontend.get_password()
        password_confirm = self.frontend.get_verified_password()
        auto_login = self.frontend.get_auto_login()

        self.preseed('passwd/user-fullname', fullname)
        self.preseed('passwd/username', username)
        # TODO: maybe encrypt these first
        self.preseed('passwd/user-password', password, escape=True)
        self.preseed('passwd/user-password-again', password_confirm,
                     escape=True)
        self.preseed_bool('passwd/auto-login', auto_login)
        self.preseed('passwd/user-uid', '')

        super(User, self).ok_handler()

    def error(self, priority, question):
        self.frontend.error_dialog(self.description(question),
                                   self.extended_description(question))
        return super(User, self).error(priority, question)
