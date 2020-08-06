import base64

import os
import time
from datetime import datetime
from io import BytesIO

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from flask import Flask, jsonify, request, send_from_directory, session
from flask_cors import CORS, cross_origin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import null
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from flask_wtf import CSRFProtect
from flask_socketio import SocketIO
import uuid
from sklearn import metrics

from auths import login_required
from common import SQLALCHEMY_DATABASE_URI, failReturn, successReturn
from stage1_2 import stage1_init, stage2_init, stage2, load_imgs, stage1_2, to_nii

# todo doctorID可以由前端给 patientId可以由前端或者直接自己查询manager 或 同局域网内关联数据库


app = Flask(__name__)
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(APP_ROOT, 'uploads')
RESULT_FOLDER = os.path.join(APP_ROOT, 'results')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULT_FOLDER'] = RESULT_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = True
app.config['WTF_CSRF_ENABLED'] = False
db = SQLAlchemy(app)
app.secret_key = os.urandom(24)

CSRFProtect(app)

# enable CORS
CORS(app, supports_credentials=True, resources={r'/*': {'origins': '*'}})
socketio = SocketIO(app, cors_allowed_origins='*')


class CTImg(db.Model):
    __tablename__ = 'ctimgs'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), unique=True)
    uploadname = db.Column(db.String(255), unique=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    type = db.Column(db.String(255), unique=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    patient = db.relationship('Patient', backref=db.backref('ctimgs', lazy='dynamic'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    docter = db.relationship('User', backref=db.backref('ctimgs', lazy='dynamic'))

    def __init__(self, filename, uploadname, img_type, patient, doctor):
        self.filename = filename
        self.type = img_type
        self.patient = patient
        self.uploadname = uploadname
        self.docter = doctor

    def __repr__(self):
        return '<DWI %r>' % self.filename


class Result(db.Model):
    __tablename__ = 'results'
    id = db.Column(db.Integer, primary_key=True)
    filename1 = db.Column(db.String(255), unique=True)
    filename2 = db.Column(db.String(255), unique=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    modeltype = db.Column(db.String(255), unique=True)
    dwi_name = db.Column(db.String(255), unique=False)
    adc_name = db.Column(db.String(255), unique=False)
    info = db.Column(db.String(255), unique=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    patient = db.relationship('Patient', backref=db.backref('results', lazy='dynamic'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    docter = db.relationship('User', backref=db.backref('results', lazy='dynamic'))
    realimg = db.Column(db.String(255), unique=True)
    roi = db.Column(db.String(255), unique=True)

    def __init__(self, filename1, filename2, modeltype, patient, doctor, dwi_name, adc_name, info):
        self.filename1 = filename1
        self.filename2 = filename2
        self.modeltype = modeltype
        self.patient = patient
        self.docter = doctor
        self.dwi_name = dwi_name
        self.adc_name = adc_name
        self.info = info

    def __repr__(self):
        return '<DWI %r>' % self.filename


class Patient(db.Model):
    __tablename__ = 'patients'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True)
    age = db.Column(db.Integer)
    sex = db.Column(db.Integer)
    info = db.Column(db.String(255))
    result = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.now)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    docter = db.relationship('User', backref=db.backref('patients', lazy='dynamic'))

    def __init__(self, username, doctor, age, sex, info, result):
        self.username = username
        self.docter = doctor
        self.age = age
        self.sex = sex
        self.info = info
        self.result = result

    def __repr__(self):
        return '<Patient %r>' % self.username


# User==Doctor
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    realname = db.Column(db.String(255), unique=False)
    userType = db.Column(db.Integer)

    def __init__(self, username, password, realname, userType=1):
        password = generate_password_hash(password)
        self.username = username
        self.password = password
        self.realname = realname
        self.userType = userType

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def to_json(self):
        return {'id': self.id, 'username': self.username,
                'realname': self.realname, 'usertype': self.userType}

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return '<User %r>' % self.username


db.create_all()


def _get_current_user():
    """
    获取当前用户
    :return: User
    """
    currentName = session["user_name"]
    if currentName:
        return User.query.filter_by(username=currentName).first()
    return null


def add_item(id, img_type, filename, uploadname):
    """
    增加ctimg信息
    :param id:
    :param img_type:
    :param filename:
    :param uploadname:
    :return: boolean
    """
    patient = Patient.query.filter_by(id=id).first()
    doctor = _get_current_user()
    if patient is None:
        return False
    ct = CTImg(filename, uploadname, img_type, patient, doctor)
    db.session.add(ct)
    db.session.commit()
    return True


def img_to_base64(img):
    """
    img转换
    :param img:
    :return: string
    """
    output_buffer = BytesIO()
    plt.imsave(output_buffer, img, cmap='gray')
    byte_data = output_buffer.getvalue()
    base64_data = base64.b64encode(byte_data)
    return "data:image/jpg;base64," + base64_data.decode('ascii')


@app.route('/api/ctUpload', methods=['POST'])
@login_required
@cross_origin()
def ct_upload():
    """
    ct图像上传
    :return: json
    """
    file = request.files['file']
    uploadname = secure_filename(file.filename)
    id = request.form['id']
    img_type = request.form['type']
    filename = img_type + "_" + uuid.uuid4().hex + ".nii.gz"
    save_path = app.config['UPLOAD_FOLDER']
    os.makedirs(save_path, exist_ok=True)
    save_file = os.path.join(save_path, filename)
    if not add_item(id, img_type, filename, uploadname):
        return failReturn("", "ct图像上传失败")
    else:
        file.save(save_file)
    return successReturn("", "ct图像上传成功")


def _get_results(id):
    """
    获取result信息
    :param id:
    :return: result
    """

    def to_dict(p):
        results = p.results.order_by(Result.timestamp).all()[::-1]
        res = []
        for r in results:
            timeArray = time.localtime(float(r.timestamp))
            stime = time.strftime('%Y-%m-%d %H:%M:%S', timeArray)
            res.append({'id': r.id, 'time': stime, 'name1': r.filename1,
                        'name2': r.filename2,
                        'modelType': r.modelType,
                        "p_name": p.username})
        return res

    patient = Patient.query.filter_by(id=id).first()
    doctor = _get_current_user()
    if doctor.userType == 1 or patient.docter == doctor:
        return to_dict(patient)
    else:
        return None


@app.route('/api/getResults', methods=['POST'])
@login_required
@cross_origin()
def get_results():
    """
    获取result
    :return: json
    """
    json = request.get_json()
    id = json['id']
    patient = _get_results(id)
    if patient:
        return successReturn({"results": patient}, "获取result成功")
    else:
        return failReturn("", "获取result失败")


def _get_inp_out(id):
    """
    获取图像结果信息
    :param id:
    :return: adc_file, dwi_file, res_file1, res_file2, info
    """
    result = Result.query.filter_by(id=id).first()
    if not result:
        return None, None, None, None, None
    adc_file = result.adc_name
    dwi_file = result.dwi_name
    res_file1 = result.filename1
    res_file2 = result.filename2
    info = result.info
    return adc_file, dwi_file, res_file1, res_file2, info


# getInpOut
@app.route('/api/getInpOut', methods=['POST'])
@login_required
@cross_origin()
def get_inp_out():
    """
    获取图像信息
    :return: json
    """
    response_object = {}
    json = request.get_json()
    id = json['id']
    adc_file, dwi_file, res_file1, res_file2, info = _get_inp_out(id)
    if adc_file or dwi_file or res_file1 or res_file2:
        if dwi_file:
            response_object['dwi_file'] = dwi_file
            dwi_file = os.path.join(app.config['UPLOAD_FOLDER'], dwi_file)
            response_object['dwi_imgs'], response_object['dwi_slices'] = get_all_slice(dwi_file)
        if adc_file:
            response_object['adc_file'] = adc_file
            adc_file = os.path.join(app.config['UPLOAD_FOLDER'], adc_file)
            response_object['adc_imgs'], response_object['adc_slices'] = get_all_slice(adc_file)
        if res_file1:
            response_object['res_file1'] = res_file1
            res_file1 = os.path.join(app.config['RESULT_FOLDER'], res_file1)
            response_object['res_imgs1'], response_object['res_slices1'] = get_all_slice(res_file1, thres=0.25)
        if res_file2:
            response_object['res_file2'] = res_file2
            res_file2 = os.path.join(app.config['RESULT_FOLDER'], res_file2)
            response_object['res_imgs2'], response_object['res_slices2'] = get_all_slice(res_file2, thres=0.25)
        if info:
            info = round(info, 2)
            response_object['info'] = info
    else:
        return failReturn("", "无数据信息")
    return successReturn(response_object, "成功获取数据信息")


def get_all_slice(filename, thres=None):
    """
    获取所有切片
    :param filename:
    :param thres:
    :return: res
    """
    if not filename:
        return None, None
    imgs = nib.load(filename).get_fdata()
    imgs = np.squeeze(imgs)
    if thres:
        imgs[imgs >= thres] = 1
        imgs[imgs < thres] = 0
    res = []
    for idx in range(imgs.shape[2]):
        res.append(img_to_base64(imgs[:, :, idx]))
    return res, str(imgs.shape[2])


@app.route('/api/ctimg', methods=['POST'])
@login_required
@cross_origin()
def get_image():
    """
    获取ct结果 dwi或者adc
    :return: json
    """
    response_object = {}
    dwi_file = request.get_json()['dwi']
    adc_file = request.get_json()['adc']

    if dwi_file:
        dwi_file = os.path.join(app.config['UPLOAD_FOLDER'], dwi_file)
        response_object['dwi_imgs'], response_object['dwi_slices'] = get_all_slice(dwi_file)
    if adc_file:
        adc_file = os.path.join(app.config['UPLOAD_FOLDER'], adc_file)
        response_object['adc_imgs'], response_object['adc_slices'] = get_all_slice(adc_file)

    return successReturn(response_object, "ct结果")


def _del_image(filename):
    """
    删除ct图像
    :param filename:
    :return: string
    """
    ctimg = CTImg.query.filter_by(filename=filename).first()
    if ctimg:
        db.session.delete(ctimg)
        db.session.commit()
        os.remove(filename)
        return "delete success"
    return "not exist"


# del_image 删除ct图像
@app.route('/api/delImage', methods=['POST'])
@login_required
@cross_origin()
def del_image():
    response_object = {
        'dwi': 'fail',
        'adc': 'fail',
    }
    dwi_file = request.get_json()['dwi_file']
    adc_file = request.get_json()['adc_file']
    if dwi_file:
        _del_image(dwi_file)
        response_object['dwi'] = 'success'
    if adc_file:
        _del_image(adc_file)
        response_object['adc'] = 'success'
    return successReturn(response_object, "删除成功")


# # todo get_model select_model 交给前端去做
# # get_model 获取当前model
# @app.route('/api/getModel', methods=['GET'])
# @login_required
# @cross_origin()
# def get_model():
#     response_object = {'status': 'success'}
#     doctor = _get_current_user()
#     if not doctor:
#         response_object['status'] = 'fail'
#     response_object['model'] = doctor.modelType
#     return jsonify(response_object)


# # select_model 选择模型
# @app.route('/api/selectModel', methods=['POST'])
# @login_required
# @cross_origin()
# def select_model():
#     response_object = {'status': 'success'}
#     model = request.get_json()['model']
#     doctor = _get_current_user()
#     if not doctor:
#         response_object['status'] = 'fail'
#     doctor.modelType = model
#     db.session.commit()
#     return jsonify(response_object)


@app.route('/api/analyze', methods=['POST'])
@login_required
@cross_origin()
def analyze():
    """
    结果分析
     "Random Forest" if r.modelType == 0 else "Random Forest+U-Net"
    :return: json
    """

    def base64(imgs):
        res = []
        for idx in range(imgs.shape[2]):
            res.append(img_to_base64(imgs[:, :, idx]))
        return res, str(imgs.shape[2])

    response_object = {}
    json = request.get_json()
    modelType = json['backmodel']
    dwi_name = json['dwi']
    adc_name = json['adc']
    id = json['id']
    if dwi_name or adc_name:
        if dwi_name:
            dwi_file = os.path.join(app.config['UPLOAD_FOLDER'], dwi_name)
        if adc_name:
            adc_file = os.path.join(app.config['UPLOAD_FOLDER'], adc_name)
    else:
        return failReturn("", "输入参数缺失")
    imgs = load_imgs(adc_file, dwi_file)
    dwi_arr = imgs.get('dwi')
    adc_arr = imgs.get('adc')
    affine = imgs.get('affine')
    if modelType == "Random Forest":
        perf_preds, nonperf_preds, info = stage2(perf_model, nonperf_model, perf_clf, nonperf_clf, dwi_arr, adc_arr,
                                                 socketio)
    else:
        perf_preds, nonperf_preds, info = stage1_2(perf_model, nonperf_model, perf_clf, nonperf_clf, dwi_arr, adc_arr,
                                                   socketio)
    perf_res = to_nii(perf_preds, affine)
    save_name1 = "perf_" + uuid.uuid4().hex + ".nii"
    save_path1 = os.path.join(app.config['RESULT_FOLDER'], save_name1)
    perf_res.to_filename(save_path1)
    nonperf_res = to_nii(nonperf_preds, affine)
    save_name2 = "nonperf_" + uuid.uuid4().hex + ".nii"
    save_path2 = os.path.join(app.config['RESULT_FOLDER'], save_name2)
    nonperf_res.to_filename(save_path2)
    patient = Patient.query.filter_by(id=id).first()
    doctor = _get_current_user()
    res_to_db = Result(save_name1, save_name2, modelType, patient, doctor, dwi_name, adc_name, info)
    db.session.add(res_to_db)
    db.session.commit()
    perf_preds[perf_preds >= 0.2] = 1
    perf_preds[perf_preds < 0.2] = 0
    nonperf_preds[nonperf_preds >= 0.2] = 1
    nonperf_preds[nonperf_preds < 0.2] = 0
    response_object['perf_res_imgs'], response_object['perf_res_slices'] = base64(perf_preds)
    response_object['nonperf_res_imgs'], response_object['nonperf_res_slices'] = base64(nonperf_preds)
    response_object['res_path1'] = save_name1
    response_object['res_path2'] = save_name2
    response_object['info'] = round(info, 2)
    return successReturn(response_object, "分析成功")


@app.route("/api/download1/<path:filename>", methods=['GET'])
@login_required
@cross_origin()
def download_file1(filename):
    """
    下载目录一
    :param filename:
    :return:
    """
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route("/api/download2/<path:filename>", methods=['GET'])
@login_required
@cross_origin()
def download_file2(filename):
    """
    下载目录二
    :param filename:
    :return:
    """
    return send_from_directory(app.config['RESULT_FOLDER'], filename)


def _del_result(id):
    """
    删除处理结果
    :param id:
    :return: boolean
    """
    res = Result.query.filter_by(id=id).first()
    if not res:
        return False
    db.session.delete(res)
    os.remove(os.path.join(app.config['RESULT_FOLDER'], res.filename1))
    os.remove(os.path.join(app.config['RESULT_FOLDER'], res.filename2))
    db.session.commit()
    return True


@app.route('/api/delResult', methods=['POST'])
@login_required
@cross_origin()
def del_result():
    """
    删除图像结果
    :return: json
    """
    id = request.get_json()['resid']
    if not _del_result(id):
        return failReturn("", "删除失败")
    return successReturn("", "删除成功")


@app.route('/api/ROI', methods=['POST'])
@login_required
@cross_origin()
def ROI_upload():
    """
    脑部梗死区上传
    :return: json
    """
    file = request.files['file']
    uploadname = secure_filename(file.filename)
    id = request.form['id']
    filename = uuid.uuid4().hex + '_' + uploadname
    save_path = app.config['UPLOAD_FOLDER']
    os.makedirs(save_path, exist_ok=True)
    save_file = os.path.join(save_path, filename)
    r = Result.query.filter_by(id=id).first()
    if not r:
        return failReturn("", "上传失败")
    else:
        if r.roi:
            os.remove(os.path.join(save_path, r.roi))
        r.roi = filename
        db.session.commit()
        file.save(save_file)
    return successReturn("", "上传成功")


@app.route('/api/realimg', methods=['POST'])
@login_required
@cross_origin()
def realimg_upload():
    """
    真实图像上传
    :return: json
    """
    file = request.files['file']
    uploadname = secure_filename(file.filename)
    id = request.form['id']
    filename = uuid.uuid4().hex + '_' + uploadname
    save_path = app.config['UPLOAD_FOLDER']
    os.makedirs(save_path, exist_ok=True)
    save_file = os.path.join(save_path, filename)
    r = Result.query.filter_by(id=id).first()
    if not r:
        return failReturn("", "上传失败")
    else:
        if r.realimg:
            os.remove(os.path.join(save_path, r.realimg))
        r.realimg = filename
        db.session.commit()
        file.save(save_file)
    return successReturn("", "上传成功")


def _get_inp_fix(id):
    result = Result.query.filter_by(id=id).first()
    if not result:
        return None, None, None, None
    adc_file = result.adc_name
    dwi_file = result.dwi_name
    realimg = result.realimg
    roi = result.roi
    return adc_file, dwi_file, realimg, roi


@app.route('/api/getInpFix', methods=['POST'])
@login_required
@cross_origin()
def get_inp_fix():
    """
    获取并修正
    :return: json
    """
    response_object = {}
    json = request.get_json()
    id = json['id']
    adc_file, dwi_file, realimg, roi = _get_inp_fix(id)
    if adc_file or dwi_file or realimg or roi:
        if dwi_file:
            response_object['dwi_file'] = dwi_file
            dwi_file = os.path.join(app.config['UPLOAD_FOLDER'], dwi_file)
            response_object['dwi_imgs'], response_object['dwi_slices'] = get_all_slice(dwi_file)
        if adc_file:
            response_object['adc_file'] = adc_file
            adc_file = os.path.join(app.config['UPLOAD_FOLDER'], adc_file)
            response_object['adc_imgs'], response_object['adc_slices'] = get_all_slice(adc_file)
        if realimg:
            response_object['realimg'] = realimg
        if roi:
            response_object['roi'] = roi

    else:
        return failReturn("", "修正失败")
    return successReturn("", "修正成功")


def _get_fix_list():
    """
    获取结果信息列表
    :return: res
    """
    doctor = _get_current_user()
    if doctor.userType == 1:
        results = Result.query.all()
        res = []
        for r in results:
            if r.realimg and r.roi:
                res.append({"id": r.id, "d_name": r.docter.username, "p_name": r.patient.username,
                            "modelType": r.modelType
                            })
        return res

    else:
        return "not allowed"


@app.route('/api/getFixList', methods=['GET'])
@login_required
@cross_origin()
def get_fix_list():
    """
    获取结果信息列表
    :return: json
    """
    res = _get_fix_list()
    if res == "not allowed":
        return failReturn("not allowed", "获取失败")
    elif res:
        return successReturn({'res': res}, "获取成功")
    else:
        return failReturn("", "获取失败")


def _del_fix(id):
    """
    删除真实图像和roi信息
    :param id:
    :return: boolean
    """
    res = Result.query.filter_by(id=id).first()
    if not res:
        return False
    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], res.realimg))
    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], res.roi))
    res.realimg = None
    res.roi = None
    db.session.commit()
    return True


@app.route('/api/delFix', methods=['POST'])
@login_required
@cross_origin()
def del_fix():
    """
    删除真实图像和roi信息
    :return: json
    """
    id = request.get_json()['resid']
    if not _del_fix(id):
        return failReturn("", "删除失败")
    return successReturn("", "删除成功")


def _eval(gt, pred, dwi):
    """
    评测
    :param gt:
    :param pred:
    :param dwi:
    :return: accuracy, specifity, sensitivity, auc
    """
    idx = np.where(dwi.flatten() > 1000)
    preds = pred.flatten()[idx]
    gts = gt.flatten()[idx]
    tn, fp, fn, tp = metrics.confusion_matrix(gts, preds > 0.15).ravel()
    sensitivity = tp / (tp + fn)
    specifity = tn / (fp + tn)
    auc = metrics.roc_auc_score(gts, preds)
    accuracy = metrics.accuracy_score(gts, preds > 0.15)
    return accuracy, specifity, sensitivity, auc


@app.route('/api/eval', methods=['POST'])
@login_required
@cross_origin()
def eval():
    """
    发起评测获得结果
    :return: json
    """
    response_object = {}
    id = request.get_json()['resid']
    dataset = request.get_json()['dataset']
    res = Result.query.filter_by(id=id).first()
    if not res:
        return failReturn("", "发起评测失败")
    roi = res.roi
    roi = nib.load(os.path.join(UPLOAD_FOLDER, roi)).get_fdata()
    roi = np.squeeze(roi)
    dwi = res.dwi_name
    dwi = nib.load(os.path.join(UPLOAD_FOLDER, dwi)).get_fdata()
    dwi = np.squeeze(dwi)
    perf = res.filename1
    perf = nib.load(os.path.join(RESULT_FOLDER, perf)).get_fdata()
    perf = np.squeeze(perf)
    nonperf = res.filename2
    nonperf = nib.load(os.path.join(RESULT_FOLDER, nonperf)).get_fdata()
    nonperf = np.squeeze(nonperf)
    if dataset == 0:
        accuracy, specifity, sensitivity, auc = _eval(roi, perf, dwi)
        response_object['eval'] = '与真实结果相比，Perfussion数据模型预测结果准确率为{}，特异度为{}，灵敏度为{}，AUC为{}'. \
            format(round(accuracy, 2), round(specifity, 2), round(sensitivity, 2), round(auc, 2))
    else:
        accuracy, specifity, sensitivity, auc = _eval(roi, nonperf, dwi)
        response_object['eval'] = '与真实结果相比，Non-Perfussion数据模型预测结果准确率为{}，特异度为{}，灵敏度为{}，AUC为{}'. \
            format(round(accuracy, 2), round(specifity, 2), round(sensitivity, 2), round(auc, 2))
    return successReturn(response_object, "发起评测成功")


if __name__ == '__main__':
    def after_request(resp):
        resp.headers['Access-Control-Allow-Credentials'] = 'true'
        return resp


    perf_model, nonperf_model = stage1_init()
    perf_clf, nonperf_clf = stage2_init()
    app.after_request(after_request)
    socketio.run(app, host='127.0.0.1', port=5051)
