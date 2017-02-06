# QLineEdit has no Signal clicked. But when clicking Search Widget, stackedWidget should show keyboeard Layout instead
# of Basket.
# Thats why focusInEvent is overwritten and a new signal, focused, is emitted, when widget is focused

from PyQt4.QtCore import pyqtSignal
from PyQt4.QtGui import QLineEdit


class MyQLineEdit(QLineEdit):

    """QLineEdit with extra signals focused() and clicked() that are emitted when the user interacts with the box"""
    focused = pyqtSignal()
    clicked = pyqtSignal()

    def focusInEvent(self, event):
        QLineEdit.focusInEvent(self, event)
        self.focused.emit()

    def mousePressEvent(self, event):
        QLineEdit.mousePressEvent(self, event)
        self.clicked.emit()
