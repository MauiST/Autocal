import sys
from PySide6.QtWidgets import QApplication
from gui.main_window import MainWindow
from gui.styles import DARK_STYLE


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
