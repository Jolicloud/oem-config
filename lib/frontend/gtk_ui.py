# -*- coding: UTF-8 -*-

# Copyright (C) 2005, 2006, 2007, 2008, 2009 Canonical Ltd.
# Copyright (C) 2007 Mario Limonciello <superm1@ubuntu.com>
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
import datetime
import gettext
import pygtk
pygtk.require('2.0')
import pango
import gobject
import gtk
import gtk.glade

from oem_config import filteredcommand, i18n, timezone_map
from oem_config.components import console_setup, language, timezone, user, \
                                  language_apply, timezone_apply, \
                                  console_setup_apply
import oem_config.emap
import oem_config.tz
from oem_config.frontend.base import BaseFrontend

PATH = '/usr/share/oem-config'
GLADEDIR = '/usr/share/oem-config/glade'

class Frontend(BaseFrontend):
    def __init__(self):
        def add_subpage(self, steps, name):
            """Inserts a subpage into the notebook.  This assumes the file
            shares the same base name as the page you are looking for."""
            gladefile = GLADEDIR + '/' + name + '.glade'
            gladexml = gtk.glade.XML(gladefile, name)
            widget = gladexml.get_widget(name)
            steps.append_page(widget)
            add_widgets(self, gladexml)
            gladexml.signal_autoconnect(self)

        def add_widgets(self, glade):
            """Makes all widgets callable by the toplevel."""
            for widget in glade.get_widget_prefix(""):
                self.all_widgets.add(widget)
                setattr(self, widget.get_name(), widget)
                # We generally want labels to be selectable so that people can
                # easily report problems in them
                # (https://launchpad.net/bugs/41618), but GTK+ likes to put
                # selectable labels in the focus chain, and I can't seem to turn
                # this off in glade and have it stick. Accordingly, make sure
                # labels are unfocusable here.
                if isinstance(widget, gtk.Label):
                    widget.set_property('can-focus', False)

        BaseFrontend.__init__(self)

        self.previous_excepthook = sys.excepthook
        sys.excepthook = self.excepthook

        self.all_widgets = set()
        self.language_questions = ('oem_config', 'language_heading_label',
                                   'step_label', 'back', 'next')
        self.current_page = None
        self.username_edited = False
        self.allowed_change_step = True
        self.allowed_go_forward = True
        self.watch = gtk.gdk.Cursor(gtk.gdk.WATCH)
        self.apply_changes = False

        # Set default language.
        dbfilter = language.Language(self, self.debconf_communicator())
        dbfilter.cleanup()
        dbfilter.db.shutdown()

        if 'OEM_CONFIG_GLADE' in os.environ:
            gladefile = os.environ['OEM_CONFIG_GLADE']
        else:
            gladefile = '%s/oem-config.glade' % GLADEDIR
        self.glade = gtk.glade.XML(gladefile)
        add_widgets(self, self.glade)

        steps = self.glade.get_widget("steps")
        for page in self.pages:
            add_subpage(self, steps, page)

        def win_size_req(win, req):
            s = win.get_screen()
            m = s.get_monitor_geometry(0)
            w = -1
            h = -1

            # What's the size of the WM border?
            total_frame = win.window.get_frame_extents()
            (cur_x, cur_y, cur_w, cur_h, depth) = win.window.get_geometry()
            wm_w = total_frame.width - cur_w
            wm_h = total_frame.height - cur_h

            if req.width > m.width - wm_w:
                w = m.width - wm_w
            if req.height > m.height - wm_h:
                h = m.height - wm_h

            win.set_size_request(w, h)
            win.resize(w, h)

        if 'OEM_CONFIG_ONLY' in os.environ:
            self.oem_config.fullscreen()
        else:
            self.oem_config.connect('size-request', win_size_req)

        self.translate_widgets()

        if 'UBIQUITY_OLD_TZMAP' in os.environ:
            self.tzmap = TimezoneMap(self)
            self.tzmap.tzmap.show()
        else:
            self.tzdb = oem_config.tz.Database()
            self.tzmap = timezone_map.TimezoneMap(self.tzdb,
                '/usr/share/oem-config/pixmaps/timezone')
            self.tzmap.connect('city-selected', self.select_city)
            self.timezone_map_window.add(self.tzmap)
            self.setup_timezone_page()
            self.tzmap.show()

        if 'OEM_CONFIG_DEBUG' in os.environ:
            self.password_debug_warning_label.show()

    def setup_timezone_page(self):
        renderer = gtk.CellRendererText()
        self.timezone_zone_combo.pack_start(renderer, True)
        self.timezone_zone_combo.add_attribute(renderer, 'text', 0)
        list_store = gtk.ListStore(gobject.TYPE_STRING)
        self.timezone_zone_combo.set_model(list_store)
        self.timezone_zone_combo.connect('changed',
            self.zone_combo_selection_changed)
        self.timezone_city_combo.connect('changed',
            self.city_combo_selection_changed)

        renderer = gtk.CellRendererText()
        self.timezone_city_combo.pack_start(renderer, True)
        self.timezone_city_combo.add_attribute(renderer, 'text', 0)
        city_store = gtk.ListStore(gobject.TYPE_STRING)
        self.timezone_city_combo.set_model(city_store)

        self.regions = {}
        for location in self.tzdb.locations:
            region, city = location.zone.replace('_', ' ').split('/', 1)
            if region in self.regions:
                self.regions[region].append(city)
            else:
                self.regions[region] = [city]

        r = self.regions.keys()
        for region in r:
            list_store.append([region])

    def excepthook(self, exctype, excvalue, exctb):
        """Crash handler."""

        if (issubclass(exctype, KeyboardInterrupt) or
            issubclass(exctype, SystemExit)):
            return

        self.post_mortem(exctype, excvalue, exctb)

        self.previous_excepthook(exctype, excvalue, exctb)

    def run(self):
        self.oem_config.show()

        if os.getuid() != 0:
            title = ('This program must be run with administrative '
                     'privileges, and cannot continue without them.')
            dialog = gtk.MessageDialog(self.oem_config, gtk.DIALOG_MODAL,
                                       gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
                                       title)
            dialog.run()
            sys.exit(1)

        self.glade.signal_autoconnect(self)

        # Some signals need to be connected by hand so that we have the
        # handler ids.
        self.username_changed_id = self.username.connect(
            'changed', self.on_username_changed)

        self.steps.set_current_page(self.steps.page_num(self.step_language))
        # TODO cjwatson 2006-07-07: why isn't on_steps_switch_page getting
        # invoked?
        self.set_current_page(self.steps.page_num(self.step_language))

        while self.current_page is not None:
            self.backup = False
            current_name = self.step_name(self.current_page)
            if current_name == 'step_language':
                self.dbfilter = language.Language(self)
            elif current_name == 'step_timezone':
                self.dbfilter = timezone.Timezone(self)
            elif current_name == 'step_keyboard':
                self.dbfilter = console_setup.ConsoleSetup(self)
            elif current_name == 'step_user':
                self.dbfilter = user.User(self)
            else:
                raise ValueError, "step %s not recognised" % current_name

            self.allow_change_step(False)
            self.dbfilter.start(auto_process=True)
            gtk.main()

            if self.backup:
                pass
            elif current_name == 'step_language':
                self.translate_widgets()
                self.steps.next_page()
            elif current_name == 'step_keyboard':
                self.info_loop(None)
                self.steps.next_page()
            elif current_name == 'step_user':
                self.allow_change_step(False)
                self.current_page = None
                self.apply_changes = True
            else:
                self.steps.next_page()

            while gtk.events_pending():
                gtk.main_iteration()

        # TODO: handle errors
        if self.apply_changes:
            dbfilter = language_apply.LanguageApply(self)
            dbfilter.run_command(auto_process=True)

            dbfilter = timezone_apply.TimezoneApply(self)
            dbfilter.run_command(auto_process=True)

            dbfilter = console_setup_apply.ConsoleSetupApply(self)
            dbfilter.run_command(auto_process=True)

        self.oem_config.hide()

        if self.apply_changes:
            return 0
        else:
            return 10

    # Internationalisation.

    def translate_widgets(self):
        if self.locale is None:
            languages = []
        else:
            languages = [self.locale]
        core_names = ['oem-config/text/%s' % q
                      for q in self.language_questions]
        for stock_item in ('go-back', 'go-forward'):
            core_names.append('oem-config/imported/%s' % stock_item)
        i18n.get_translations(languages=languages, core_names=core_names)

        for widget in self.all_widgets:
            self.translate_widget(widget, self.locale)

    def translate_widget(self, widget, lang):
        if isinstance(widget, gtk.Button) and widget.get_use_stock():
            widget.set_label(widget.get_label())

        text = self.get_string(widget.get_name(), lang)
        if text is None:
            return
        name = widget.get_name()

        if isinstance(widget, gtk.Label):
            if name == 'step_label':
                curstep = '?'
                if self.current_page is not None:
                    # TODO cjwatson 2009-01-20: This is a compromise. It
                    # doesn't work with multi-page steps (e.g. partitioning
                    # in ubiquity), but it simplifies page configuration
                    # quite a bit.
                    curstep = str(self.current_page + 1)
                text = text.replace('${INDEX}', curstep)
                text = text.replace('${TOTAL}', str(self.steps.get_n_pages()))
            widget.set_text(text)

            # Ideally, these attributes would be in the glade file somehow ...
            textlen = len(text.encode("UTF-8"))
            if 'heading_label' in name:
                attrs = pango.AttrList()
                attrs.insert(pango.AttrScale(pango.SCALE_LARGE, 0, textlen))
                attrs.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, textlen))
                widget.set_attributes(attrs)
            elif 'extra_label' in name:
                attrs = pango.AttrList()
                attrs.insert(pango.AttrStyle(pango.STYLE_ITALIC, 0, textlen))
                widget.set_attributes(attrs)
            elif 'warning_label' in name:
                attrs = pango.AttrList()
                attrs.insert(pango.AttrWeight(pango.WEIGHT_BOLD, 0, textlen))
                widget.set_attributes(attrs)

        elif isinstance(widget, gtk.Button):
            # TODO evand 2007-06-26: LP #122141 causes a crash unless we keep a
            # reference to the button image.
            tempref = widget.get_image()

            question = i18n.map_widget_name(widget.get_name())
            widget.set_label(text)
            if question.startswith('oem-config/imported/'):
                stock_id = question[18:]
                widget.set_use_stock(False)
                widget.set_image(gtk.image_new_from_stock(
                    'gtk-%s' % stock_id, gtk.ICON_SIZE_BUTTON))

        elif isinstance(widget, gtk.Window):
            widget.set_title(text)

    # I/O helpers.

    def watch_debconf_fd (self, from_debconf, process_input):
        gobject.io_add_watch(from_debconf,
                             gobject.IO_IN | gobject.IO_ERR | gobject.IO_HUP,
                             self.watch_debconf_fd_helper, process_input)


    def watch_debconf_fd_helper (self, source, cb_condition, callback):
        debconf_condition = 0
        if (cb_condition & gobject.IO_IN) != 0:
            debconf_condition |= filteredcommand.DEBCONF_IO_IN
        if (cb_condition & gobject.IO_ERR) != 0:
            debconf_condition |= filteredcommand.DEBCONF_IO_ERR
        if (cb_condition & gobject.IO_HUP) != 0:
            debconf_condition |= filteredcommand.DEBCONF_IO_HUP

        return callback(source, debconf_condition)

    def error_dialog (self, title, msg):
        # TODO: cancel button as well if capb backup
        self.allow_change_step(True)
        if not msg:
            msg = title
        dialog = gtk.MessageDialog(self.oem_config, gtk.DIALOG_MODAL,
                                   gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, msg)
        dialog.set_title(title)
        dialog.run()
        dialog.hide()

    def question_dialog (self, title, msg, options, use_templates=True):
        self.allow_change_step(True)
        if not msg:
            msg = title
        buttons = []
        for option in options:
            if use_templates:
                text = self.get_string(option)
            else:
                text = option
            if text is None:
                text = option
            # Work around PyGTK bug; each button text must actually be a
            # subtype of str, which unicode isn't.
            text = str(text)
            buttons.extend((text, len(buttons) / 2 + 1))
        dialog = gtk.Dialog(title, self.oem_config,
                            gtk.DIALOG_MODAL, tuple(buttons))
        vbox = gtk.VBox()
        vbox.set_border_width(5)
        label = gtk.Label(msg)
        label.set_line_wrap(True)
        label.set_selectable(True)
        vbox.pack_start(label)
        vbox.show_all()
        dialog.vbox.pack_start(vbox)
        response = dialog.run()
        dialog.hide()
        if response < 0:
            # something other than a button press, probably destroyed
            return None
        else:
            return options[response - 1]

    # Run the UI's main loop until it returns control to us.
    def run_main_loop(self):
        if not self.apply_changes:
            self.allow_change_step(True)
        gtk.main()

    # Return control to the next level up.
    def quit_main_loop(self):
        gtk.main_quit()

    # Step-handling functions.

    def step_name(self, step_index):
        return self.steps.get_nth_page(step_index).get_name()

    def set_current_page(self, current):
        self.current_page = current
        self.translate_widget(self.step_label, self.locale)
        if current == 0:
            self.back.hide()
        else:
            self.back.show()

    def on_steps_switch_page(self, foo, bar, current):
        self.set_current_page(current)

    def allow_change_step(self, allowed):
        if allowed:
            cursor = None
        else:
            cursor = self.watch
        self.oem_config.window.set_cursor(cursor)
        self.back.set_sensitive(allowed)
        self.next.set_sensitive(allowed and self.allowed_go_forward)
        # Work around http://bugzilla.gnome.org/show_bug.cgi?id=56070
        if self.back.get_property('visible') and allowed:
            self.back.hide()
            self.back.show()
        if (self.next.get_property('visible') and
            allowed and self.allowed_go_forward):
            self.next.hide()
            self.next.show()
            self.next.grab_default()
        self.allowed_change_step = allowed

    def allow_go_forward(self, allowed):
        self.next.set_sensitive(allowed and self.allowed_change_step)
        # Work around http://bugzilla.gnome.org/show_bug.cgi?id=56070
        if (self.next.get_property('visible') and
            allowed and self.allowed_change_step):
            self.next.hide()
            self.next.show()
            self.next.grab_default()
        self.allowed_go_forward = allowed

    def debconffilter_done(self, dbfilter):
        if BaseFrontend.debconffilter_done(self, dbfilter):
            gtk.main_quit()

    def on_back_clicked(self, widget):
        if not self.allowed_change_step:
            return

        self.allow_change_step(False)
        self.allow_go_forward(True)

        self.backup = True
        self.steps.prev_page()
        if self.dbfilter is not None:
            self.dbfilter.cancel_handler()
            # expect recursive main loops to be exited and
            # debconffilter_done() to be called when the filter exits

        if not self.oem_config.get_focus():
            self.oem_config.child_focus(gtk.DIR_TAB_FORWARD)

    def on_next_clicked(self, widget):
        if not self.allowed_change_step or not self.allowed_go_forward:
            return

        self.allow_change_step(False)

        step = self.step_name(self.steps.get_current_page())

        if step == "step_user":
            self.username_error_box.hide()
            self.password_error_box.hide()

        if self.dbfilter is not None:
            self.dbfilter.ok_handler()
            # expect recursive main loops to be exited and
            # debconffilter_done() to be called when the filter exits

        if not self.oem_config.get_focus():
            self.oem_config.child_focus(gtk.DIR_TAB_FORWARD)

    # Callbacks provided to components.

    def zone_combo_selection_changed(self, widget):
        i = self.timezone_zone_combo.get_active()
        m = self.timezone_zone_combo.get_model()
        region = m[i][0]

        m = self.timezone_city_combo.get_model()
        m.clear()
        for city in self.regions[region]:
            m.append([city])

    def city_combo_selection_changed(self, widget):
        i = self.timezone_zone_combo.get_active()
        m = self.timezone_zone_combo.get_model()
        region = m[i][0]

        i = self.timezone_city_combo.get_active()
        if i < 0:
            # There's no selection yet.
            return
        m = self.timezone_city_combo.get_model()
        city = m[i][0].replace(' ', '_')
        city = region + '/' + city
        self.tzmap.select_city(city)

    def select_city(self, widget, city):
        region, city = city.replace('_', ' ').split('/', 1)
        m = self.timezone_zone_combo.get_model()
        iterator = m.get_iter_first()
        while iterator:
            if m[iterator][0] == region:
                self.timezone_zone_combo.set_active_iter(iterator)
                break
            iterator = m.iter_next(iterator)

        m = self.timezone_city_combo.get_model()
        iterator = m.get_iter_first()
        while iterator:
            if m[iterator][0] == city:
                self.timezone_city_combo.set_active_iter(iterator)
                break
            iterator = m.iter_next(iterator)

    def selected_language (self):
        model = self.language_iconview.get_model()
        items = self.language_iconview.get_selected_items()
        if not items:
            return ''
        iterator = model.get_iter(items[0])
        if iterator is not None:
            value = unicode(model.get_value(iterator, 0))
            return self.language_choice_map[value][1]

    def set_language_choices(self, choices, choice_map):
        BaseFrontend.set_language_choices(self, choices, choice_map)
        self.language_iconview.connect('selection-changed',
                          self.on_language_iconview_selection_changed)
        list_store = gtk.ListStore(gobject.TYPE_STRING)
        self.language_iconview.set_model(list_store)
        self.language_iconview.set_text_column(0)
        for choice in choices:
            list_store.append([choice])

    def set_language(self, language):
        model = self.language_iconview.get_model()
        iterator = model.iter_children(None)
        while iterator is not None:
            if unicode(model.get_value(iterator, 0)) == language:
                path = model.get_path(iterator)
                self.language_iconview.select_path(path)
                self.language_iconview.scroll_to_path(path, True, 0.5, 0.5)
                break
            iterator = model.iter_next(iterator)

    def get_language(self):
        model = self.language_iconview.get_model()
        items = self.language_iconview.get_selected_items()
        if not items:
            return 'C'
        iterator = model.get_iter(items[0])
        if iterator is None:
            return 'C'
        else:
            value = unicode(model.get_value(iterator, 0))
            return self.language_choice_map[value][1]

    def on_language_iconview_item_activated (self, iconview, path):
        self.next.activate()

    def on_language_iconview_selection_changed (self, iconview):
        lang = self.selected_language()
        if lang:
            # strip encoding; we use UTF-8 internally no matter what
            lang = lang.split('.')[0].lower()
            for widget in self.language_questions:
                self.translate_widget(getattr(self, widget), lang)

    def set_timezone (self, timezone):
        self.select_city(None, timezone)

    def get_timezone (self):
        i = self.timezone_zone_combo.get_active()
        m = self.timezone_zone_combo.get_model()
        region = m[i][0]

        i = self.timezone_city_combo.get_active()
        m = self.timezone_city_combo.get_model()
        city = m[i][0].replace(' ', '_')
        city = region + '/' + city
        return city

    def set_keyboard_choices(self, choices):
        layouts = gtk.ListStore(gobject.TYPE_STRING)
        self.keyboardlayoutview.set_model(layouts)
        for v in sorted(choices):
            layouts.append([v])

        if len(self.keyboardlayoutview.get_columns()) < 1:
            column = gtk.TreeViewColumn("Layout", gtk.CellRendererText(), text=0)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            self.keyboardlayoutview.append_column(column)
            selection = self.keyboardlayoutview.get_selection()
            selection.connect('changed',
                              self.on_keyboard_layout_selected)

        if self.current_layout is not None:
            self.set_keyboard(self.current_layout)

    def set_keyboard (self, layout):
        BaseFrontend.set_keyboard(self, layout)
        model = self.keyboardlayoutview.get_model()
        if model is None:
            return
        iterator = model.iter_children(None)
        while iterator is not None:
            if unicode(model.get_value(iterator, 0)) == layout:
                path = model.get_path(iterator)
                self.keyboardlayoutview.get_selection().select_path(path)
                self.keyboardlayoutview.scroll_to_cell(
                    path, use_align=True, row_align=0.5)
                break
            iterator = model.iter_next(iterator)

    def get_keyboard (self):
        selection = self.keyboardlayoutview.get_selection()
        (model, iterator) = selection.get_selected()
        if iterator is None:
            return None
        else:
            return unicode(model.get_value(iterator, 0))

    def set_keyboard_variant_choices(self, choices):
        variants = gtk.ListStore(gobject.TYPE_STRING)
        self.keyboardvariantview.set_model(variants)
        for v in sorted(choices):
            variants.append([v])

        if len(self.keyboardvariantview.get_columns()) < 1:
            column = gtk.TreeViewColumn("Variant", gtk.CellRendererText(), text=0)
            column.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
            self.keyboardvariantview.append_column(column)
            selection = self.keyboardvariantview.get_selection()
            selection.connect('changed',
                              self.on_keyboard_variant_selected)

    def set_keyboard_variant (self, variant):
        model = self.keyboardvariantview.get_model()
        if model is None:
            return
        iterator = model.iter_children(None)
        while iterator is not None:
            if unicode(model.get_value(iterator, 0)) == variant:
                path = model.get_path(iterator)
                self.keyboardvariantview.get_selection().select_path(path)
                self.keyboardvariantview.scroll_to_cell(
                    path, use_align=True, row_align=0.5)
                break
            iterator = model.iter_next(iterator)

    def get_keyboard_variant (self):
        selection = self.keyboardvariantview.get_selection()
        (model, iterator) = selection.get_selected()
        if iterator is None:
            return None
        else:
            return unicode(model.get_value(iterator, 0))

    def on_keyboardlayoutview_row_activated(self, treeview, path, view_column):
        self.next.activate()

    def on_keyboard_layout_selected(self, start_editing, *args):
        if isinstance(self.dbfilter, console_setup.ConsoleSetup):
            layout = self.get_keyboard()
            if layout is not None:
                self.current_layout = layout
                self.dbfilter.change_layout(layout)

    def on_keyboardvariantview_row_activated(self, treeview, path,
                                             view_column):
        self.next.activate()

    def on_keyboard_variant_selected(self, start_editing, *args):
        if isinstance(self.dbfilter, console_setup.ConsoleSetup):
            layout = self.get_keyboard()
            variant = self.get_keyboard_variant()
            if layout is not None and variant is not None:
                self.dbfilter.apply_keyboard(layout, variant)

    def set_fullname(self, value):
        self.fullname.set_text(value)

    def get_fullname(self):
        return self.fullname.get_text()

    def set_username(self, value):
        self.username.set_text(value)

    def get_username(self):
        return self.username.get_text()

    def get_password(self):
        return self.password.get_text()

    def get_verified_password(self):
        return self.verified_password.get_text()

    def get_auto_login(self):
        return self.auto_login.get_active()

    def username_error(self, msg):
        self.username_error_reason.set_text(msg)
        self.username_error_box.show()

    def password_error(self, msg):
        self.password_error_reason.set_text(msg)
        self.password_error_box.show()

    def info_loop(self, widget):
        if (widget is not None and widget.get_name() == 'fullname' and
            not self.username_edited):
            self.username.handler_block(self.username_changed_id)
            new_username = widget.get_text().split(' ')[0]
            new_username = new_username.encode('ascii', 'ascii_transliterate')
            new_username = new_username.lower()
            self.username.set_text(new_username)
            self.username.handler_unblock(self.username_changed_id)

        complete = True
        for name in ('username', 'password', 'verified_password'):
            if getattr(self, name).get_text() == '':
                complete = False
        self.allow_go_forward(complete)

    def on_username_changed(self, widget):
        self.username_edited = (widget.get_text() != '')


# Much of this timezone map widget is a rough translation of
# gnome-system-tools/src/time/tz-map.c. Thanks to Hans Petter Jansson
# <hpj@ximian.com> for that.

NORMAL_RGBA = 0xc070a0ffL
HOVER_RGBA = 0xffff60ffL
SELECTED_1_RGBA = 0xff60e0ffL
SELECTED_2_RGBA = 0x000000ffL

class TimezoneMap(object):
    def __init__(self, frontend):
        self.frontend = frontend
        self.tzdb = oem_config.tz.Database()
        self.tzmap = oem_config.emap.EMap()
        self.update_timeout = None
        self.point_selected = None
        self.point_hover = None
        self.location_selected = None

        self.tzmap.set_smooth_zoom(False)
        zoom_in_file = os.path.join(PATH, 'pixmaps', 'zoom-in.png')
        if os.path.exists(zoom_in_file):
            display = self.frontend.oem_config.get_display()
            pixbuf = gtk.gdk.pixbuf_new_from_file(zoom_in_file)
            self.cursor_zoom_in = gtk.gdk.Cursor(display, pixbuf, 10, 10)
        else:
            self.cursor_zoom_in = None

        self.tzmap.add_events(gtk.gdk.LEAVE_NOTIFY_MASK |
                              gtk.gdk.VISIBILITY_NOTIFY_MASK)

        self.frontend.timezone_map_window.add(self.tzmap)

        timezone_city_combo = self.frontend.timezone_city_combo

        renderer = gtk.CellRendererText()
        timezone_city_combo.pack_start(renderer, True)
        timezone_city_combo.add_attribute(renderer, 'text', 0)
        list_store = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        timezone_city_combo.set_model(list_store)

        prev_continent = ''
        for location in self.tzdb.locations:
            self.tzmap.add_point("", location.longitude, location.latitude,
                                 NORMAL_RGBA)
            zone_bits = location.zone.split('/')
            if len(zone_bits) == 1:
                continue
            continent = zone_bits[0]
            if continent != prev_continent:
                list_store.append(['', None])
                list_store.append(["--- %s ---" % continent, None])
                prev_continent = continent
            human_zone = '/'.join(zone_bits[1:]).replace('_', ' ')
            list_store.append([human_zone, location.zone])

        self.tzmap.connect("map-event", self.mapped)
        self.tzmap.connect("unmap-event", self.unmapped)
        self.tzmap.connect("motion-notify-event", self.motion)
        self.tzmap.connect("button-press-event", self.button_pressed)
        self.tzmap.connect("leave-notify-event", self.out_map)

        timezone_city_combo.connect("changed", self.city_changed)

    def set_city_text(self, name):
        model = self.frontend.timezone_city_combo.get_model()
        iterator = model.get_iter_first()
        while iterator is not None:
            location = model.get_value(iterator, 1)
            if location == name:
                self.frontend.timezone_city_combo.set_active_iter(iterator)
                break
            iterator = model.iter_next(iterator)

    def set_zone_text(self, location):
        offset = location.utc_offset
        if offset >= datetime.timedelta(0):
            minuteoffset = int(offset.seconds / 60)
        else:
            minuteoffset = int(offset.seconds / 60 - 1440)
        if location.zone_letters == 'GMT':
            text = location.zone_letters
        else:
            text = "%s (GMT%+d:%02d)" % (location.zone_letters,
                                         minuteoffset / 60, minuteoffset % 60)
        self.frontend.timezone_zone_text.set_text(text)
        translations = gettext.translation('iso_3166',
                                           languages=[self.frontend.locale],
                                           fallback=True)
        self.frontend.timezone_country_text.set_text(
            translations.ugettext(location.human_country))
        self.update_current_time()

    def update_current_time(self):
        if self.location_selected is not None:
            try:
                now = datetime.datetime.now(self.location_selected.info)
                self.frontend.timezone_time_text.set_text(now.strftime('%X'))
            except ValueError:
                # Some versions of Python have problems with clocks set
                # before the epoch (http://python.org/sf/1646728).
                self.frontend.timezone_time_text.set_text('<clock error>')

    def set_tz_from_name(self, name):
        (longitude, latitude) = (0.0, 0.0)

        for location in self.tzdb.locations:
            if location.zone == name:
                (longitude, latitude) = (location.longitude, location.latitude)
                break
        else:
            return

        if self.point_selected is not None:
            self.tzmap.point_set_color_rgba(self.point_selected, NORMAL_RGBA)

        self.point_selected = self.tzmap.get_closest_point(longitude, latitude,
                                                           False)

        self.location_selected = location
        self.set_city_text(self.location_selected.zone)
        self.set_zone_text(self.location_selected)
        self.frontend.allow_go_forward(True)

    def city_changed(self, widget):
        iterator = widget.get_active_iter()
        if iterator is not None:
            model = widget.get_model()
            location = model.get_value(iterator, 1)
            if location is not None:
                self.set_tz_from_name(location)

    def get_selected_tz_name(self):
        if self.location_selected is not None:
            return self.location_selected.zone
        else:
            return None

    def location_from_point(self, point):
        if point is None:
            return None

        (longitude, latitude) = point.get_location()

        best_location = None
        best_distance = None
        for location in self.tzdb.locations:
            if (abs(location.longitude - longitude) <= 1.0 and
                abs(location.latitude - latitude) <= 1.0):
                distance = ((location.longitude - longitude) ** 2 +
                            (location.latitude - latitude) ** 2) ** 0.5
                if best_distance is None or distance < best_distance:
                    best_location = location
                    best_distance = distance

        return best_location

    def timeout(self):
        self.update_current_time()

        if self.point_selected is None:
            return True

        if self.point_selected.get_color_rgba() == SELECTED_1_RGBA:
            self.tzmap.point_set_color_rgba(self.point_selected,
                                            SELECTED_2_RGBA)
        else:
            self.tzmap.point_set_color_rgba(self.point_selected,
                                            SELECTED_1_RGBA)

        return True

    def mapped(self, widget, event):
        if self.update_timeout is None:
            self.update_timeout = gobject.timeout_add(100, self.timeout)

    def unmapped(self, widget, event):
        if self.update_timeout is not None:
            gobject.source_remove(self.update_timeout)
            self.update_timeout = None

    def motion(self, widget, event):
        if self.tzmap.get_magnification() <= 1.0:
            if self.cursor_zoom_in is not None:
                self.frontend.oem_config.window.set_cursor(self.cursor_zoom_in)
        else:
            self.frontend.oem_config.window.set_cursor(None)

            (longitude, latitude) = self.tzmap.window_to_world(event.x,
                                                               event.y)

            if (self.point_hover is not None and
                self.point_hover != self.point_selected):
                self.tzmap.point_set_color_rgba(self.point_hover, NORMAL_RGBA)

            self.point_hover = self.tzmap.get_closest_point(longitude,
                                                            latitude, True)

            if self.point_hover != self.point_selected:
                self.tzmap.point_set_color_rgba(self.point_hover, HOVER_RGBA)

        return True

    def out_map(self, widget, event):
        if event.mode != gtk.gdk.CROSSING_NORMAL:
            return False

        if (self.point_hover is not None and
            self.point_hover != self.point_selected):
            self.tzmap.point_set_color_rgba(self.point_hover, NORMAL_RGBA)

        self.point_hover = None

        self.frontend.oem_config.window.set_cursor(None)

        return True

    def button_pressed(self, widget, event):
        (longitude, latitude) = self.tzmap.window_to_world(event.x, event.y)

        if event.button != 1:
            self.tzmap.zoom_out()
            if self.cursor_zoom_in is not None:
                self.frontend.oem_config.window.set_cursor(self.cursor_zoom_in)
        elif self.tzmap.get_magnification() <= 1.0:
            self.tzmap.zoom_to_location(longitude, latitude)
            if self.cursor_zoom_in is not None:
                self.frontend.oem_config.window.set_cursor(None)
        else:
            if self.point_selected is not None:
                self.tzmap.point_set_color_rgba(self.point_selected,
                                                NORMAL_RGBA)
            self.point_selected = self.point_hover

            new_location_selected = \
                self.location_from_point(self.point_selected)
            if new_location_selected is not None:
                old_city = self.get_selected_tz_name()
                if old_city is None or old_city != new_location_selected.zone:
                    self.set_city_text(new_location_selected.zone)
                    self.set_zone_text(new_location_selected)
            self.location_selected = new_location_selected
            self.frontend.allow_go_forward(self.location_selected is not None)

        return True
