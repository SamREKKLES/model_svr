KEY = "zhaohan-manager"
ISS = "zhaohan"
DB_USER = 'root'
DB_PASSWORD = 'zj123456'
DB_HOST = 'cdb-fum3r7xh.gz.tencentcdb.com:10161'
DB_DB = 'manager'
SQLALCHEMY_DATABASE_URI = 'mysql://' + DB_USER + ':' + DB_PASSWORD + '@' + DB_HOST + '/' + DB_DB


def successReturn(data, msg):
    return {
        "status": 'success',
        "data": data,
        "msg": msg
    }


def failReturn(data, msg):
    return {
        "status": 'fail',
        "data": data,
        "msg": msg
    }