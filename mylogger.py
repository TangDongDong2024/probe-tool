import logging
import os
import traceback
from logging.handlers import RotatingFileHandler


class MyLogger:
    def __init__(self, name, level=logging.DEBUG, console=True, file_path=None, file_size=10*1024*1024, backup_count=10):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        formatter = logging.Formatter('%(asctime)s %(filename)s[line:%(lineno)d] %(thread)d %(levelname)s %(message)s')
        # console handle
        if console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)
        # file handle
        if file_path:
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)  # create path if not exists
                file_handler = RotatingFileHandler(file_path, maxBytes=file_size, backupCount=backup_count)
                file_handler.setLevel(level)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            except Exception:
                traceback.print_exc()


    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)

    def exception(self, msg, *args, **kwargs):
        self.logger.exception(msg, *args, **kwargs)
    def setLogLevel(self,level):
        for handler in self.logger.handlers:
            handler.setLevel(logging.DEBUG)
            self.logger.debug('Debug logging enabled')
            # if isinstance(handler, type(logging.StreamHandler())):
            #     handler.setLevel(logging.DEBUG)
            #     self.logger.debug('Debug logging enabled')


    def close(self):
        for hdlr in self.logger.handlers:
            hdlr.close()
            self.logger.removeHandler(hdlr)