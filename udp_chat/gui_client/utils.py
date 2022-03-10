"""Utility widgets used by other parts of the GUI."""
from PyQt5.QtCore import QSize, QRectF
from PyQt5.QtWidgets import QLabel, QFrame, QSizePolicy, QGraphicsPixmapItem, QGraphicsEffect, QGraphicsScene
from PyQt5.QtGui import QMovie, QPixmap, QPainter


class CircularSpinner(QLabel):
    """Circular spinner widget used to indicate indefinite progress."""
  
    def __init__(self, parent, width: int = 40, height: int = 40):
        super().__init__(parent)
        size = QSize(width, height)
        self.setMinimumSize(size)
        self.setMaximumSize(size)
        movie = QMovie(":/loading-circular.gif")
        movie.setScaledSize(size)
        self.setMovie(movie)
        movie.start()

    def startAnimation(self):
        self.movie().start()


class LineWidget(QFrame):
    """From https://stackoverflow.com/questions/10053839/how-does-designer-create-a-line-widget."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFrameShape(QFrame.HLine)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)
        self.setStyleSheet("border-color: black;")


def applyEffectToPixmap(pmap: QPixmap, effect: QGraphicsEffect) -> QPixmap:
    """From https://stackoverflow.com/questions/3903223/qt4-how-to-blur-qpixmap-image."""
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem()
    item.setPixmap(pmap)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    ptr = QPainter(pmap)
    scene.render(ptr, QRectF(), QRectF(0,0, pmap.width(), pmap.height()) )
    return pmap
