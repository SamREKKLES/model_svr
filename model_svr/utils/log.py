import logging
import os
from logging import handlers

log_error = os.path.join(os.getcwd(), "log", "error_log")
log_info = os.path.join(os.getcwd(), "log", "all_log")


def logError(message):
    logger = logging.getLogger('error.log')

    #  这里进行判断，如果logger.handlers列表为空，则添加，否则，直接去写日志
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s')
        sh = logging.StreamHandler()
        th = handlers.TimedRotatingFileHandler(filename=log_error, when="D", interval=1, backupCount=7, encoding='utf-8')
        sh.setFormatter(formatter)
        th.setFormatter(formatter)
        logger.addHandler(sh)
        logger.addHandler(th)

    logger.exception(message)


def logInfo(message):
    logger = logging.getLogger('all.log')

    #  这里进行判断，如果logger.handlers列表为空，则添加，否则，直接去写日志
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s')
        sh = logging.StreamHandler()
        th = handlers.TimedRotatingFileHandler(filename=log_info, when="D", interval=1, backupCount=7, encoding='utf-8')
        sh.setFormatter(formatter)
        th.setFormatter(formatter)
        logger.addHandler(sh)
        logger.addHandler(th)

    logger.info(message)
