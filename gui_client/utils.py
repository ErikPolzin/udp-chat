"""Utility widgets used by other parts of the GUI."""
from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QLabel, QFrame, QSizePolicy
from PyQt5.QtGui import QMovie


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