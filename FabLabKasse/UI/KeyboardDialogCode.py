#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
#
# FabLabKasse, a Point-of-Sale Software for FabLabs and other public and trust-based workshops.
# Copyright (C) 2015  Julian Hammer <julian.hammer@fablab.fau.de>
#                     Maximilian Gaukler <max@fablab.fau.de>
#                     Timo Voigt <timo@fablab.fau.de>
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# General Public License as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with this program. If not,
# see <http://www.gnu.org/licenses/>.

from PyQt4 import QtGui
from uic_generated.KeyboardDialog import Ui_KeyboardDialog

class KeyboardDialog(QtGui.QDialog, Ui_KeyboardDialog):
    '''
    d = KeyboardDialog.askText('What?', parent=my_pyqt_window)
    if d == None:
        print "Aborted."
    else:
        print "You entered:" + d
    '''
    
    @staticmethod
    def askText(question, parent):
        d = KeyboardDialog(parent, question)
        if d.exec_():
            return d.text()
        else:
            return None

    def __init__(self, parent, question='What: '):
        QtGui.QDialog.__init__(self, parent)
        self.setupUi(self)
        
        self.caps = True
        
        self.label.setText(question)
        self.setWindowTitle(question)
        
        # [a-z0-9] + umlaute + sz
        for c in list('abcdefghijklmnopqrstuvwxyz0123456789') + ['ue', 'ae', 'oe', 'sz', 'komma',
                'dot', 'minus', 'space']:
            btn = getattr(self, "pushButton_"+c)
            btn.clicked.connect(self.charKey)
        
        # Special keys: backspace, enter, abort and shift
        self.pushButton_enter.clicked.connect(self.accept)
        self.pushButton_backspace.clicked.connect(self.backspace)
        self.pushButton_abort.clicked.connect(self.reject)
        self.pushButton_shift.clicked.connect(self.shift)
    
    def text(self):
        return unicode(self.lineEdit.text())
    
    def charKey(self):
        pos = self.lineEdit.cursorPosition()
        
        oldtext = self.lineEdit.text()
        c = self.sender().text()
        if not c:
            c = ' '
        self.lineEdit.setText(oldtext[:pos]+c+oldtext[pos:])
        
        self.lineEdit.setCursorPosition(pos+1)
        
        if self.caps:
            self.shift()
    
    def backspace(self):
        oldtext = self.lineEdit.text()
        pos = self.lineEdit.cursorPosition()
        self.lineEdit.setText(oldtext[:pos-1]+oldtext[pos:])
        self.lineEdit.setCursorPosition(pos-1)
    
    def shift(self):
        self.caps = not self.caps
        
        for c in list('abcdefghijklmnopqrstuvwxyz0123456789')+['ue','ae','oe']:
            btn = getattr(self, "pushButton_"+c)
            if self.caps:
                btn.setText(unicode(btn.text()).upper())
            else:
                btn.setText(unicode(btn.text()).lower())
