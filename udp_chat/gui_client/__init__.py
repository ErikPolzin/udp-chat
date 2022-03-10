import asyncio
import logging
import sys

from PyQt5.QtWidgets import QApplication

from udp_chat.server import get_host_and_port
from .main_window import MainWindow
from . import resources

try:
    from qasync import QEventLoop
except ImportError:
    logging.info("The GUI needs qasync to run, please install it!")
    sys.exit(0)


def main():
    logging.basicConfig(level=logging.DEBUG)
    server_addr = get_host_and_port()
    app = QApplication([])

    window = MainWindow(server_addr)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    with loop:
        # Create a separate task to run PyQt and asyncio alongside oneanother
        asyncio.create_task(window.create_client(server_addr))
        loop.run_forever()
        logging.info("Application exited.")


if __name__ == "__main__":
    main()
