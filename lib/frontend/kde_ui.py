# -*- coding: utf-8 -*-

# Copyright (C) 2006, 2007 Anirudh Ramesh
# Copyright (C) 2006, 2007, 2008, 2009 Canonical Ltd.
# Written by Anirudh Ramesh <abattoir@abattoir.in>.
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
#
# https://wiki.kubuntu.org/KubuntuOEMInstaller
# Bugs: https://launchpad.net/ubuntu/+source/oem-config/+filebug

import sys
import os
import datetime
import gettext
import syslog

from PyKDE4.kdecore import ki18n, KAboutData, KCmdLineArgs
from PyKDE4.kdeui import KApplication, KMainWindow, KIcon
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import uic

from oem_config import filteredcommand, i18n
from oem_config.components import console_setup, language, timezone, user, \
                                  language_apply, timezone_apply, \
                                  console_setup_apply
import oem_config.tz
from oem_config.frontend.base import BaseFrontend

from Timezone import TimezoneMap

UIDIR = '/usr/share/oem-config/qt'

class OEMConfUI(QWidget):

    def __init__(self, parent):
        QWidget.__init__(self, parent)
        uic.loadUi("%s/sysconf.ui" % UIDIR, self)
        self.setAutoFillBackground(True)

    def setFrontend(self, fe):
        self.frontend = fe

    def resizeEvent(self, event):
        if QFile.exists("/usr/share/wallpapers/Blue_Curl/contents/images/1920x1200.jpg"):
            imageFile = "/usr/share/wallpapers/Blue_Curl/contents/images/1920x1200.jpg"
        else:
            return
        pixmapUnscaled = QPixmap()
        loaded = pixmapUnscaled.load(imageFile)
        pixmap = pixmapUnscaled.scaled(QSize(self.width(), self.height()), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        palette = self.palette()
        palette.setBrush(self.backgroundRole(),QBrush(pixmap))
        self.setPalette(palette)

class Frontend(BaseFrontend):
    def __init__(self):
        BaseFrontend.__init__(self)

        self.previous_excepthook = sys.excepthook
        sys.excepthook = self.excepthook

        self.debconf_callbacks = {}
        self.language_questions = ('oem_config', 'language_label',
                                   'language_heading_label',
                                   'timezone_heading_label',
                                   'keyboard_heading_label',
                                   'user_heading_label',
                                   'back', 'next')
        self.current_step = None
        # Set default language.
        dbfilter = language.Language(self, self.debconf_communicator())
        dbfilter.cleanup()
        dbfilter.db.shutdown()
        self.allowed_change_step = True
        self.allowed_go_forward = True
        self.mainLoopRunning = False
        self.apply_changes = False

        appName = "oem-config"
        catalog = ""
        programName = ki18n("OEM Config")
        version = "1.0"
        description = ki18n("Sets up the system")
        license = KAboutData.License_GPL
        copyright = ki18n("2006, 2007 Anirudh Ramesh. 2008 Canonical Ltd.")
        text = ki18n("none")
        homePage = "http://www.kubuntu.org"
        bugEmail = ""

        aboutData = KAboutData(appName, catalog, programName, version, description,
                               license, copyright, text, homePage, bugEmail)

        KCmdLineArgs.init(['oem-config', '-style=oxygen'], aboutData)

        self.app = KApplication()
        # We want to hide the minimise button if running in the ubiquity-only mode (no desktop)
        # To achieve this we need to set window flags to Dialog but we also need a parent widget which is showing
        # else Qt tried to be clever and puts the minimise button back
        self.parentWidget = QWidget()
        self.parentWidget.show()

        # The parent for our actual user interface window, this is needed only because Oxygen widget 
        # style refuses to draw our background on a top level widget
        self.parent2 = QWidget(self.parentWidget)
        self.parent2.setAutoFillBackground(True)
        self.parent2.setWindowState(Qt.WindowFullScreen)
        self.parent2.setWindowFlags(Qt.Dialog)
        layout = QVBoxLayout(self.parent2)
        layout.setContentsMargins(0, 0, 0, 0)

        self.userinterface = OEMConfUI(self.parent2)
        self.userinterface.setFrontend(self)
        layout.addWidget(self.userinterface)
        self.parent2.show()

        self.userinterface.next.setIcon(KIcon("go-next"))
        self.userinterface.back.setIcon(KIcon("go-previous"))

        self.translate_widgets()

        self.customize_installer()
        
        self.tzmap = TimezoneMap(self)
        map_vbox = QVBoxLayout(self.userinterface.map_frame)
        map_vbox.setMargin(0)
        map_vbox.addWidget(self.tzmap)

    def excepthook(self, exctype, excvalue, exctb):
        """Crash handler."""

        if (issubclass(exctype, KeyboardInterrupt) or
            issubclass(exctype, SystemExit)):
            return

        self.post_mortem(exctype, excvalue, exctb)

        self.previous_excepthook(exctype, excvalue, exctb)

    def run(self):
        if os.getuid() != 0:
            title = ('This installer must be run with administrative '
                     'privileges, and cannot continue without them.')
            result = QMessageBox.critical(self.userinterface, "Must be root",
                                          title)
            sys.exit(1)

        self.userinterface.setCursor(QCursor(Qt.ArrowCursor))

        #Signals and Slots
        self.app.connect(self.userinterface.next,SIGNAL("clicked()"),self.on_next_clicked)
        self.app.connect(self.userinterface.back,SIGNAL("clicked()"),self.on_back_clicked)
        self.app.connect(self.userinterface.language_list, SIGNAL("itemSelectionChanged()"), self.on_language_treeview_selection_changed)
        self.app.connect(self.userinterface.keyboard_list_1, SIGNAL("itemSelectionChanged()"), self.on_keyboard_layout_selected)
        self.app.connect(self.userinterface.keyboard_list_2, SIGNAL("itemSelectionChanged()"), self.on_keyboard_variant_selected)

        first_step = "step_language"
        self.userinterface.stackedWidget.setCurrentWidget(self.userinterface.step_language)
        self.current_step = self.get_current_step()
        self.set_current_page()
        while self.current_step is not None:
            self.backup = False
            self.current_step = self.get_current_step()
            if self.current_step == 'step_language':
                self.dbfilter = language.Language(self)
            elif self.current_step == 'step_keyboard':
                self.dbfilter = console_setup.ConsoleSetup(self)
            elif self.current_step == 'step_timezone':
                self.dbfilter = timezone.Timezone(self)
            elif self.current_step == 'step_user':
                self.dbfilter = user.User(self)
            else:
                raise ValueError, "step %s not recognised" % self.current_step
            self.allow_change_step(False)
            self.dbfilter.start(auto_process=True)
            self.app.exec_()
            self.app.processEvents()
            curr = str(self.get_current_step())

            if self.backup:
                pass
            elif self.current_step == 'step_user':
                self.allow_change_step(False)
                self.current_step = None
                self.apply_changes = True
            else:
                if self.current_step == 'step_language':
                    self.translate_widgets()
                self.userinterface.stackedWidget.setCurrentIndex(self.pages.index(curr) + 1)
                self.set_current_page()
            self.app.processEvents()
        if self.apply_changes:
            dbfilter = language_apply.LanguageApply(self)
            dbfilter.run_command(auto_process=True)

            dbfilter = timezone_apply.TimezoneApply(self)
            dbfilter.run_command(auto_process=True)

            dbfilter = console_setup_apply.ConsoleSetupApply(self)
            dbfilter.run_command(auto_process=True)

            return 0
        else:
            return 10


    def customize_installer(self):
        self.step_icon_size = QSize(32,32)
        self.step_icons = [self.userinterface.step_icon_lang, self.userinterface.step_icon_loc, \
                           self.userinterface.step_icon_key, self.userinterface.step_icon_user]
        self.step_labels = [self.userinterface.language_heading_label, self.userinterface.timezone_heading_label, \
                            self.userinterface.keyboard_heading_label, self.userinterface.user_heading_label]
        if QFile.exists("../../../usr/lib/kde4/share/icons/oxygen/32x32/apps/preferences-desktop-locale.png"):
            self.step_icons_path_prefix = "../../../usr/lib/kde4/share/icons/oxygen/32x32/apps/"
            self.step_icons_path = ["preferences-desktop-locale.png", "preferences-system-time.png", "preferences-desktop-keyboard.png", "system-users.png"]
        else:
            self.step_icons_path_prefix = "../../../usr/share/icons/default.kde/32x32/apps/"
            self.step_icons_path = ["locale.png", "clock.png", "keyboard_layout.png", "userconfig.png"]
        self.step_labels_text = [self.userinterface.language_heading_label.text(),self.userinterface.timezone_heading_label.text(), \
                                self.userinterface.keyboard_heading_label.text(), self.userinterface.user_heading_label.text()]
        for icon in range(len(self.pages)):
            self.step_icons[icon].setPixmap(QPixmap(str(self.step_icons_path_prefix+self.step_icons_path[icon])))

    # Internationalisation.

    def translate_widgets(self, parentWidget=None):
        if self.locale is None:
            languages = []
        else:
            languages = [self.locale]
        core_names = ['oem-config/text/%s' % q
                      for q in self.language_questions]
        for stock_item in ('go-back', 'go-forward'):
            core_names.append('oem-config/imported/%s' % stock_item)
        i18n.get_translations(languages=languages, core_names=core_names)

        self.translate_widget_children(parentWidget)

    def translate_widget_children(self, parentWidget=None):
        if parentWidget is None:
            parentWidget = self.userinterface

        self.translate_widget(parentWidget, self.locale)
        if parentWidget.children() is not None:
            for widget in parentWidget.children():
                self.translate_widget_children(widget)

    def translate_widget(self, widget, lang):
        if not isinstance(widget, QWidget):
            return

        name = widget.objectName()

        text = self.get_string(name, lang)

        if str(name) == 'language_label':
            text = self.get_string('language_heading_label', lang)

        if str(name) == 'next':
            text = self.get_string('oem-config/imported/go-forward', lang)

        if str(name) == 'back':
            text = self.get_string('oem-config/imported/go-back', lang)

        if str(name) == "SysConf":
            text = self.get_string("oem_config", lang)

        if text is None:
            return

        if isinstance(widget, QLabel):
            if 'heading_label' in name:
                widget.setText("""<html><head><meta name="qrichtext" content="1" /><style type="text/css">
p, li { white-space: pre-wrap; }
</style></head><body style=" font-family:'Sans Serif'; font-size:9pt; font-weight:400; font-style:normal; text-decoration:none;">
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;">  <span style=" font-size:13pt; color:gray;">""" +
                               text + "</span></p></body></html>")
            elif 'extra_label' in name:
                widget.setText("""<html><head><meta name="qrichtext" content="1" /><style type="text/css">
p, li { white-space: pre-wrap; }
</style></head><body style=" font-family:'Sans Serif'; font-size:9pt; font-weight:400; font-style:normal; text-decoration:none;">
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" font-style:italic;">""" +
                               text + "</span></p></body></html>")                
            else:
                widget.setText(text)

        elif isinstance(widget, QPushButton):
            widget.setText(text.replace('_', '&', 1))

        elif isinstance(widget, QWidget) and str(name) == "SysConf":
            widget.setWindowTitle(text)

        else:
            print "WARNING: unknown widget: " + name


    def on_keyboard_layout_selected(self):
        if isinstance(self.dbfilter, console_setup.ConsoleSetup):
            layout = self.get_keyboard()
            if layout is not None:
                self.current_layout = layout
                self.dbfilter.change_layout(layout)

    def on_keyboard_variant_selected(self):
        if isinstance(self.dbfilter, console_setup.ConsoleSetup):
            layout = self.get_keyboard()
            variant = self.get_keyboard_variant()
            if layout is not None and variant is not None:
                self.dbfilter.apply_keyboard(layout, variant)

    def selected_language(self):
        selection = self.userinterface.language_list.selectedItems()
        if len(selection) == 1:
            value = unicode(selection[0].text())
            return self.language_choice_map[value][1]
        else:
            return ''

    def set_language_choices(self, choices, choice_map):
        BaseFrontend.set_language_choices(self, choices, choice_map)
        self.userinterface.language_list.clear()
        self.lang_store = QStringList()
        for choice in choices:
            self.lang_store.append(QString(choice))
        self.userinterface.language_list.addItems(self.lang_store)


    def set_language(self, language):
        index = self.lang_store.indexOf(QRegExp("^"+language+"$"))
        if index != -1:
            self.userinterface.language_list.setCurrentRow(index)

    def get_language(self):
        value = unicode(self.userinterface.language_list.currentItem().text())
        return self.language_choice_map[value][1]

    def on_language_treeview_selection_changed(self):
        lang = self.selected_language()
        if lang:
            # strip encoding; we use UTF-8 internally no matter what
            lang = lang.split('.')[0].lower()
            for widget in (self.userinterface, self.userinterface.language_label, self.userinterface.welcome_label, self.userinterface.back, self.userinterface.next):
                self.translate_widget(widget, lang)
            for step in range(len(self.pages)):
                self.translate_widget(self.step_labels[step], lang)
                self.step_labels_text[step] = self.step_labels[step].text()

    def set_timezone (self, timezone):
        self.tzmap.set_tz_from_name(timezone)

    def get_timezone (self):
        return self.tzmap.get_selected_tz_name()

    def set_keyboard_choices(self, choices):
        self.userinterface.keyboard_list_1.clear()
        self.key_store_1 = QStringList()
        for choice in sorted(choices):
            self.key_store_1.append(QString(choice))
        self.userinterface.keyboard_list_1.addItems(self.key_store_1)

        if self.current_layout is not None:
            self.set_keyboard(self.current_layout)

    def set_keyboard(self, layout):
        BaseFrontend.set_keyboard(self, layout)
        index = self.key_store_1.indexOf(QRegExp("^"+layout+"$"))
        if index != -1:
            self.userinterface.keyboard_list_1.setCurrentRow(index)

    def get_keyboard(self):
        return unicode(self.userinterface.keyboard_list_1.currentItem().text())

    def set_keyboard_variant_choices(self, choices):
        self.userinterface.keyboard_list_2.clear()
        self.key_store_2 = QStringList()
        for choice in sorted(choices):
            self.key_store_2.append(QString(choice))
        self.userinterface.keyboard_list_2.addItems(self.key_store_2)

    def set_keyboard_variant(self, variant):
        index = self.key_store_2.indexOf(QRegExp("^"+variant+"$"))
        if index != -1:
            self.userinterface.keyboard_list_2.setCurrentRow(index)

    def get_keyboard_variant(self):
        return unicode(self.userinterface.keyboard_list_2.currentItem().text())

    def set_timezone (self, timezone):
        self.tzmap.set_timezone(timezone)

    def get_timezone (self):
        return self.tzmap.get_timezone()

    def set_fullname(self, value):
        self.userinterface.name_ledit.setText(value)

    def get_fullname(self):
        return unicode(self.userinterface.name_ledit.text())

    def set_username(self, value):
        self.userinterface.uname_ledit.setText(value)

    def get_username(self):
        return unicode(self.userinterface.uname_ledit.text())

    def get_password(self):
        return unicode(self.userinterface.pass_ledit_1.text())

    def get_verified_password(self):
        return unicode(self.userinterface.pass_ledit_2.text())

    def get_auto_login(self):
        return False

    def watch_debconf_fd (self, from_debconf, process_input):
        self.debconf_fd_counter = 0
        self.socketNotifierRead = QSocketNotifier(from_debconf, QSocketNotifier.Read, self.app)
        self.app.connect(self.socketNotifierRead, SIGNAL("activated(int)"), self.watch_debconf_fd_helper_read)

        self.socketNotifierWrite = QSocketNotifier(from_debconf, QSocketNotifier.Write, self.app)
        self.app.connect(self.socketNotifierWrite, SIGNAL("activated(int)"), self.watch_debconf_fd_helper_write)

        self.socketNotifierException = QSocketNotifier(from_debconf, QSocketNotifier.Exception, self.app)
        self.app.connect(self.socketNotifierException, SIGNAL("activated(int)"), self.watch_debconf_fd_helper_exception)

        self.debconf_callbacks[from_debconf] = process_input
        self.current_debconf_fd = from_debconf


    def watch_debconf_fd_helper_read (self, source):
        self.debconf_fd_counter += 1
        debconf_condition = 0
        debconf_condition |= filteredcommand.DEBCONF_IO_IN
        self.debconf_callbacks[source](source, debconf_condition)

    def watch_debconf_fd_helper_write(self, source):
        debconf_condition = 0
        debconf_condition |= filteredcommand.DEBCONF_IO_OUT
        self.debconf_callbacks[source](source, debconf_condition)

    def watch_debconf_fd_helper_exception(self, source):
        debconf_condition = 0
        debconf_condition |= filteredcommand.DEBCONF_IO_ERR
        self.debconf_callbacks[source](source, debconf_condition)

    def debconffilter_done (self, dbfilter):
        ##FIXME in Qt 4 without this disconnect it calls watch_debconf_fd_helper_read once more causing
        ## a crash after the keyboard stage.  No idea why.
        self.app.disconnect(self.socketNotifierRead, SIGNAL("activated(int)"), self.watch_debconf_fd_helper_read)
        # TODO cjwatson 2006-02-10: handle dbfilter.status
        self.app.disconnect(self.socketNotifierWrite, SIGNAL("activated(int)"), self.watch_debconf_fd_helper_write)
        self.app.disconnect(self.socketNotifierException, SIGNAL("activated(int)"), self.watch_debconf_fd_helper_exception)
        if BaseFrontend.debconffilter_done(self, dbfilter):
            self.app.exit()

    def error_dialog (self, title, msg):
        self.allow_change_step(True)
        # TODO: cancel button as well if capb backup
        QMessageBox.warning(self.userinterface, title, msg, QMessageBox.Ok)

    def question_dialog (self, title, msg, options, use_templates=True):
        # I doubt we'll ever need more than three buttons.
        assert len(options) <= 3, options

        self.allow_change_step(True)
        buttons = {}
        messageBox = QMessageBox(QMessageBox.Question, title, msg, QMessageBox.NoButton, self.userinterface)
        for option in options:
            if use_templates:
                text = self.get_string(option)
            else:
                text = option
            if text is None:
                text = option
            # Convention for options is to have the affirmative action last; KDE
            # convention is to have it first.
            if option == options[-1]:
                button = messageBox.addButton(text, QMessageBox.AcceptRole)
            else:
                button = messageBox.addButton(text, QMessageBox.RejectRole)
            buttons[button] = option

        response = messageBox.exec_()

        if response < 0:
            return None
        else:
            return buttons[messageBox.clickedButton()]

    def run_main_loop (self):
        if not self.apply_changes:
            self.allow_change_step(True)
        #self.app.exec_()   ##FIXME Qt 4 won't allow nested main loops, here it just returns directly
        self.mainLoopRunning = True
        while self.mainLoopRunning:    # nasty, but works OK
            self.app.processEvents()

    def quit_main_loop (self):
        self.mainLoopRunning = False

    def on_back_clicked(self):
        curr = str(self.get_current_step())
        self.backup = True
        if self.dbfilter is not None:
            self.userinterface.stackedWidget.setCurrentIndex(self.pages.index(curr) - 1)
            self.allow_change_step(False)
            self.dbfilter.cancel_handler()
            self.set_current_page()
            # expect recursive main loops to be exited and
            # debconffilter_done() to be called when the filter exits

    def on_next_clicked(self):
        if self.dbfilter is not None:
            self.allow_change_step(False)
            self.dbfilter.ok_handler()

    def set_current_page(self):
        current_name = self.get_current_step()
        current_page = self.pages.index(str(current_name))
        if current_name == 'step_language':
            self.userinterface.back.hide()
        else:
            self.userinterface.back.show()
        if current_name == 'step_user':
            #FIXME needs i18n(Finish)
            self.userinterface.next.setIcon(KIcon("dialog-ok"))
        else:
            self.userinterface.next.setIcon(KIcon("go-next"))
        for icon in self.step_icons:
            pixmap = QIcon(icon.pixmap()).pixmap(self.step_icon_size, QIcon.Disabled)
            icon.setPixmap(pixmap)
        for step in range(len(self.pages)):
            self.step_labels_text[step].replace("p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">  <span style=\" font-size:13pt; font-weight:800; font-style:italic;\">","<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">  <span style=\" font-size:13pt; color:gray;\">")
            self.step_labels[step].setText(self.step_labels_text[step])
        current_icon = self.step_icons[current_page]
        current_pixmap = QPixmap(str(self.step_icons_path_prefix+self.step_icons_path[current_page]))
        current_icon.setPixmap(current_pixmap)
        current_label_text = self.step_labels_text[current_page]
        current_label_text.replace("<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">  <span style=\" font-size:13pt; color:gray;\">","<p style=\" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;\">  <span style=\" font-size:13pt; font-weight:800; font-style:italic;\">")
        self.step_labels[current_page].setText(current_label_text)

    def allow_change_step(self, allowed):
        if allowed:
            cursor = QCursor(Qt.ArrowCursor)
        else:
            cursor = QCursor(Qt.WaitCursor)
        self.userinterface.setCursor(cursor)

    def allow_go_forward(self, allowed):
        self.userinterface.next.setEnabled(allowed and self.allowed_change_step)
        self.allowed_go_forward = allowed

    def get_current_step(self):
        return self.userinterface.stackedWidget.currentWidget().objectName()

