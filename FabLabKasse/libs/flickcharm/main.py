from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtWebKit import *
import random
import traceback
import sys

from flickcharm import *

ITEM_WIDTH = 300
ITEM_HEIGHT = 30

class TextItem(QGraphicsItem):
    def __init__(self, str):
        QGraphicsItem.__init__(self)
        list = str.split()
        self.str1 = list[0]
        self.str2 = list[1]
        self.font1 = QFont("Lucida Grande")
        self.font2 = QFont("Lucida Grande")
        self.font1.setBold(True)
        self.font1.setPixelSize(ITEM_HEIGHT / 2)
        self.font2.setPixelSize(ITEM_HEIGHT / 2)
        self.offset = QFontMetrics(self.font1).width(self.str1) + 15    
        
    def boundingRect(self):
        return QRectF(0, 0, ITEM_WIDTH, ITEM_HEIGHT)
    
    def paint(self, painter, option, widget):
        if option.state & QStyle.State_Selected: 
            painter.fillRect(self.boundingRect(), QColor(0, 128, 240))
            painter.setPen(Qt.white)
        else:
            painter.setPen(Qt.lightGray)
            painter.drawRect(self.boundingRect())
            painter.setPen(Qt.black)
        painter.setFont(self.font1)
        painter.drawText(QRect(10, 0, self.offset, ITEM_HEIGHT), 
                         Qt.AlignVCenter, self.str1)
        painter.setFont(self.font2)
        painter.drawText(QRect(self.offset, 0, ITEM_WIDTH, ITEM_HEIGHT), 
                         Qt.AlignVCenter, self.str2)


def colorPairs(max):
    # capitalize the first letter
    colors = []
    for c in QColor.colorNames():
        colors.append(str(c[0]).upper() + str(c)[1:])

    # combine two colors, e.g. "lime skyblue"
    combinedColors = []
    num = len(colors)
    for i in range(num):
        for j in range(num):
            combinedColors.append("%s %s" % (colors[i], colors[j]))
            
    # randomize it
    colors = []
    while len(combinedColors):
        i = random.randint(0, len(combinedColors) - 1)
        colors.append(combinedColors[i])
        del(combinedColors[i])
        if len(colors) == max:
            break

    return colors
  

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    colors = colorPairs(5000)
    scene = QGraphicsScene()
    scene.setItemIndexMethod(QGraphicsScene.NoIndex)
    i = 0
    for c in colors:
        item = TextItem(c)
        scene.addItem(item)
        item.setPos(0, i * ITEM_HEIGHT)
        item.setFlag(QGraphicsItem.ItemIsSelectable, True)
        i += 1
        
    scene.setItemIndexMethod(QGraphicsScene.BspTreeIndex)

    canvas = QGraphicsView()
    canvas.setScene(scene)
    canvas.setRenderHints(QPainter.TextAntialiasing)
    canvas.setFrameShape(QFrame.NoFrame)
    canvas.setWindowTitle("Flickable Canvas")
    canvas.show()

    web = QWebView()
    web.setUrl(QUrl("frankenstein.html"))
    web.setWindowTitle("Flickable Web View")
    web.show()
    
    charm = FlickCharm()
    charm.activateOn(canvas)
    charm.activateOn(web)
    
    sys.exit(app.exec_())
