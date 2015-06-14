from DialogBoxUi import *
class DialogBox(QtGui.QDialog, Ui_DialogBoxUi):
    def __init__(self, parent,  text="no text"):
        QtGui.QDialog.__init__(self,parent)
        self.setupUi(self)
        self.label.setText(text)
