import json
import smtplib
from datetime import date, datetime
from email.mime.text import MIMEText

from utils.log import logInfo, logError

KEY = "zhaohan-manager"
ISS = "zhaohan"
DB_USER = 'root'
DB_PASSWORD = 'zj123456'
DB_HOST = 'cdb-fum3r7xh.gz.tencentcdb.com:10161'
DB_DB = 'manager'
SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://' + DB_USER + ':' + DB_PASSWORD + '@' + DB_HOST + '/' + DB_DB
SWAGGER_TITLE = "Model_svr 算法部分"
SWAGGER_DESC = "算法部分接口文档"
MAIL_USER = 'zju205@126.com'
MAIL_PASS = 'TUVNEXOWFMTJASLN'
MAIL_HOST = 'smtp.126.com'
MAIL_REC = ['393707734@qq.com', 'xhzhao@zju.edu.cn']


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


def emailSent(content, sub):
    logInfo("email sent !!!")
    msg = MIMEText(content.encode('utf8'), 'plain', 'utf-8')
    # 邮件主题
    msg['Subject'] = sub
    # 发送方信息
    msg['From'] = MAIL_USER
    # 接受方信息
    msg['To'] = ",".join(MAIL_REC)
    # 登录并发送邮件
    try:
        smtpObj = smtplib.SMTP()
        # 连接到服务器
        smtpObj.connect(MAIL_HOST, 25)
        # 登录到服务器
        smtpObj.login(MAIL_USER, MAIL_PASS)
        # 发送
        smtpObj.sendmail(
            MAIL_USER, MAIL_REC, msg.as_string())
        # 退出
        smtpObj.quit()
        logInfo('send email success')
    except smtplib.SMTPException as e:
        logError(e, 'send email fail')  # 打印错误
