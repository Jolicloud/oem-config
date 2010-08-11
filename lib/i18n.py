# -*- coding: UTF-8 -*-

# Copyright (C) 2006, 2007 Canonical Ltd.
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

import re
import subprocess
import codecs

_supported_locales = None

def get_supported_locales():
    """Returns a list of all locales supported by the installation system."""
    global _supported_locales
    if _supported_locales is None:
        _supported_locales = {}
        supported = open('/usr/share/i18n/SUPPORTED')
        for line in supported:
            (locale, charset) = line.split(None, 1)
            _supported_locales[locale] = charset
        supported.close()
    return _supported_locales


_translations = None

def get_translations(languages=None, core_names=[]):
    """Returns a dictionary {name: {language: description}} of translatable
    strings.

    If languages is set to a list, then only languages in that list will be
    translated. If core_names is also set to a list, then any names in that
    list will still be translated into all languages. If either is set, then
    the dictionary returned will be built from scratch; otherwise, the last
    cached version will be returned."""

    global _translations
    if _translations is None or languages is not None or len(core_names) > 0:
        if languages is None:
            use_langs = None
        else:
            use_langs = set('c')
            for lang in languages:
                ll_cc = lang.lower().split('.')[0]
                ll = ll_cc.split('_')[0]
                use_langs.add(ll_cc)
                use_langs.add(ll)

        _translations = {}
        devnull = open('/dev/null', 'w')
        db = subprocess.Popen(
            ['debconf-copydb', 'templatedb', 'pipe',
             '--config=Name:pipe', '--config=Driver:Pipe',
             '--config=InFd:none',
             '--pattern=^oem-config'],
            stdout=subprocess.PIPE, stderr=devnull)
        question = None
        descriptions = {}
        fieldsplitter = re.compile(r':\s*')

        for line in db.stdout:
            line = line.rstrip('\n')
            if ':' not in line:
                if question is not None:
                    _translations[question] = descriptions
                    descriptions = {}
                    question = None
                continue

            (name, value) = fieldsplitter.split(line, 1)
            if value == '':
                continue
            name = name.lower()
            if name == 'name':
                question = value
            elif name.startswith('description'):
                namebits = name.split('-', 1)
                if len(namebits) == 1:
                    lang = 'c'
                else:
                    lang = namebits[1].lower()
                    # TODO: recode from specified encoding
                    lang = lang.split('.')[0]
                if (use_langs is None or lang in use_langs or
                    question in core_names):
                    if (question is not None and
                        question.startswith('oem-config/imported/')):
                        # strip context if necessary
                        if '|' in value:
                            value = value.split('|', 1)[1]
                    descriptions[lang] = value.replace('\\n', '\n')
            elif name.startswith('extended_description'):
                namebits = name.split('-', 1)
                if len(namebits) == 1:
                    lang = 'c'
                else:
                    lang = namebits[1].lower()
                    # TODO: recode from specified encoding
                    lang = lang.split('.')[0]
                if (use_langs is None or lang in use_langs or
                    question in core_names):
                    if (question is not None and
                        question.startswith('oem-config/imported/')):
                        # strip context if necessary
                        if '|' in value:
                            value = value.split('|', 1)[1]
                    if lang not in descriptions:
                        descriptions[lang] = value.replace('\\n', '\n')

        db.wait()
        devnull.close()

    return _translations

string_questions = {
    'language_label': 'oem-config/text/language_heading_label',
    # TODO: it would be nice to have a neater way to handle stock buttons
    'back': 'oem-config/imported/go-back',
    'next': 'oem-config/imported/go-forward',
}

def map_widget_name(name):
    """Map a widget name to its translatable template."""
    if '/' in name:
        question = name
    elif name in string_questions:
        question = string_questions[name]
    else:
        question = 'oem-config/text/%s' % name
    return question

def get_string(name, lang):
    """Get the translation of a single string."""
    question = map_widget_name(name)
    translations = get_translations()
    if question not in translations:
        return None

    if lang is None:
        lang = 'c'
    else:
        lang = lang.lower()

    if lang in translations[question]:
        text = translations[question][lang]
    else:
        ll_cc = lang.split('.')[0]
        ll = ll_cc.split('_')[0]
        if ll_cc in translations[question]:
            text = translations[question][ll_cc]
        elif ll in translations[question]:
            text = translations[question][ll]
        else:
            text = translations[question]['c']

    return unicode(text, 'utf-8', 'replace')


# Based on code by Walter Dörwald:
# http://mail.python.org/pipermail/python-list/2007-January/424460.html
def ascii_transliterate(exc):
    if not isinstance(exc, UnicodeEncodeError):
        raise TypeError("don't know how to handle %r" % exc)
    import unicodedata
    s = unicodedata.normalize('NFD', exc.object[exc.start])[:1]
    if ord(s) in range(128):
        return s, exc.start + 1
    else:
        return u'', exc.start + 1

codecs.register_error('ascii_transliterate', ascii_transliterate)
