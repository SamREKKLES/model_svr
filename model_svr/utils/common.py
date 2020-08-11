import json
from datetime import date, datetime

from utils.log import logInfo, logError

KEY = "zhaohan-manager"
ISS = "zhaohan"
DB_USER = 'root'
DB_PASSWORD = 'zj123456'
DB_HOST = 'cdb-fum3r7xh.gz.tencentcdb.com:10161'
DB_DB = 'manager'
SQLALCHEMY_DATABASE_URI = 'mysql://' + DB_USER + ':' + DB_PASSWORD + '@' + DB_HOST + '/' + DB_DB
SWAGGER_TITLE = "Model_svr 算法部分"
SWAGGER_DESC = "算法部分接口文档"


def successReturn(data, msg):
    logInfo("msg: " + msg)
    return json.dumps({
        "status": "success",
        "data": data,
        "msg": msg
    }, ensure_ascii=False, cls=ComplexEncoder)


def failReturn(data, msg):
    logError("data: " + str(data) + " msg: " + msg)
    return json.dumps({
        "status": "fail",
        "data": data,
        "msg": msg
    }, ensure_ascii=False, cls=ComplexEncoder)


class ComplexEncoder(json.JSONEncoder):
    """
    处理datetime error问题
    """
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, date):
            return obj.strftime('%Y-%m-%d')
        else:
            return json.JSONEncoder.default(self, obj)
