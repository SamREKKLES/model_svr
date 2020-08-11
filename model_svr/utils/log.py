import logging
from logging import handlers


def logError(message):
    logger = logging.getLogger('error.log')

    #  这里进行判断，如果logger.handlers列表为空，则添加，否则，直接去写日志
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s')
        sh = logging.StreamHandler()
        th = handlers.TimedRotatingFileHandler(filename='log\\error_log', when="D", interval=1, backupCount=7, encoding='utf-8')
        sh.setFormatter(formatter)
        th.setFormatter(formatter)
        logger.addHandler(sh)
        logger.addHandler(th)

    logger.error(message)


def logInfo(message):
    logger = logging.getLogger('all.log')

    #  这里进行判断，如果logger.handlers列表为空，则添加，否则，直接去写日志
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(pathname)s[line:%(lineno)d] - %(levelname)s: %(message)s')
        sh = logging.StreamHandler()
        th = handlers.TimedRotatingFileHandler(filename='log\\all_log', when="D", interval=1, backupCount=7, encoding='utf-8')
        sh.setFormatter(formatter)
        th.setFormatter(formatter)
        logger.addHandler(sh)
        logger.addHandler(th)

    logger.info(message)
