from datetime import datetime, timedelta
from functools import wraps
from flask import request, session

from utils import log
from utils.common import ISS, KEY, failReturn
import jwt


def generate_access_token(user_id, algorithm: str = 'HS256', exp: float = 2):
    """
    生成access_token
    :param user_id:
    :param algorithm:加密算法
    :param exp:过期时间
    :return:token
    """

    now = datetime.utcnow()
    exp_datetime = now + timedelta(hours=exp)
    access_payload = {
        'exp': exp_datetime,
        'flag': 0,  # 标识是否为一次性token，0是，1不是
        'iat': now,  # 开始时间
        'iss': ISS,  # 签名
        'user_id': user_id  # 自定义部分
    }
    access_token = jwt.encode(access_payload, KEY, algorithm=algorithm)
    return access_token


def generate_refresh_token(user_id, algorithm: str = 'HS256', fresh: float = 1):
    """
    生成refresh_token

    :param user_id:
    :param algorithm:加密算法
    :param fresh:过期时间
    :return:token
    """
    now = datetime.utcnow()
    # 刷新时间为1天
    exp_datetime = now + timedelta(days=fresh)
    refresh_payload = {
        'exp': exp_datetime,
        'flag': 1,  # 标识是否为一次性token，0是，1不是
        'iat': now,  # 开始时间
        'iss': ISS,  # 签名，
        'user_id': user_id  # 自定义部分
    }

    refresh_token = jwt.encode(refresh_payload, KEY, algorithm=algorithm)
    return refresh_token


def decode_auth_token(token: str):
    """
    解密token
    :param token:token字符串
    :return:
    """
    try:
        # 取消过期时间验证
        # payload = jwt.decode(token, key, options={'verify_exp': False})
        payload = jwt.decode(token, key=KEY)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, jwt.InvalidSignatureError):
        return ""
    else:
        return payload


def identify(auth_header: str):
    """
    用户鉴权
    :return:
    """
    if auth_header:
        payload = decode_auth_token(auth_header)
        if not payload:
            return False
        if "user_id" in payload and "flag" in payload:
            if payload["flag"] == 1:
                # 用来获取新access_token的refresh_token无法获取数据
                return False
            elif payload["flag"] == 0:
                return payload["user_id"]
            else:
                # 其他状态暂不允许
                return False
        else:
            return False
    else:
        return False


def login_required(f):
    """
    登陆保护，验证用户是否登陆
    :param f:
    :return:
    """

    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", default=None)
        if not token:
            log.logError("login_required: 未登录请先登陆")
            return failReturn("", "未登录请先登陆")
        user_id = identify(token)
        if not user_id:
            log.logError("login_required: 未登录请先登陆")
            return failReturn("", "未登录请先登陆")
        # 获取到用户并写入到session中,方便后续使用
        session["user_id"] = user_id
        return f(*args, **kwargs)

    return wrapper
