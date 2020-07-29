import base64
import os
import time
from io import BytesIO

import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
from flask import Flask, jsonify, request, send_from_directory, render_template
from flask_cors import CORS, cross_origin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from flask_login import login_user, logout_user, login_required, LoginManager, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField
from wtforms.validators import ValidationError, Length

from flask_wtf import CSRFProtect
from flask_socketio import SocketIO
import uuid
from sklearn import metrics
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
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///manager.db' + '?check_same_thread=False'
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
    filename = db.Column(db.String(120), unique=True)
    uploadname = db.Column(db.String(120), unique=False)
    time = db.Column(db.String(10), unique=False)
    type = db.Column(db.String(10), unique=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    patient = db.relationship('Patient', backref=db.backref('ctimgs', lazy='dynamic'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    docter = db.relationship('User', backref=db.backref('ctimgs', lazy='dynamic'))

    def __init__(self, filename, uploadname, img_type, patient, doctor, cttime=None):
        self.filename = filename
        if cttime is None:
            cttime = time.time()
        self.time = cttime
        self.type = img_type
        self.patient = patient
        self.uploadname = uploadname
        self.docter = doctor

    def __repr__(self):
        return '<DWI %r>' % self.filename


class Result(db.Model):
    __tablename__ = 'results'
    id = db.Column(db.Integer, primary_key=True)
    filename1 = db.Column(db.String(120), unique=True)
    filename2 = db.Column(db.String(120), unique=True)
    time = db.Column(db.String(10), unique=False)
    modelType = db.Column(db.Integer)
    dwi_name = db.Column(db.String(120), unique=False)
    adc_name = db.Column(db.String(120), unique=False)
    info = db.Column(db.Float, unique=False)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'))
    patient = db.relationship('Patient', backref=db.backref('results', lazy='dynamic'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    docter = db.relationship('User', backref=db.backref('results', lazy='dynamic'))
    realimg = db.Column(db.String(120), unique=True)
    roi = db.Column(db.String(120), unique=True)

    def __init__(self, filename1, filename2, modelType, patient, doctor, dwi_name, adc_name, info, cttime=None):
        self.filename1 = filename1
        self.filename2 = filename2
        if cttime is None:
            cttime = time.time()
        self.time = cttime
        self.modelType = modelType
        self.patient = patient
        self.docter = doctor
        self.dwi_name = dwi_name
        self.adc_name = adc_name
        self.info = info

    def __repr__(self):
        return '<DWI %r>' % self.filename


db.create_all()

FILE_LIST = []


# model_svr
def add_item(id, img_type, filename, uploadname, cttime=None):
    patient = Patient.query.filter_by(id=id).first()
    doctor = _get_current_user()
    if patient is None:
        return False
    ct = CTImg(filename, uploadname, img_type, patient, doctor, cttime)
    db.session.add(ct)
    db.session.commit()
    return "add successfully!"


# model_svr
def img_to_base64(img):
    output_buffer = BytesIO()
    plt.imsave(output_buffer, img, cmap='gray')
    # img.save(output_buffer, format='JPEG')
    byte_data = output_buffer.getvalue()
    base64_data = base64.b64encode(byte_data)
    return "data:image/jpg;base64," + base64_data.decode('ascii')


# model_svr
@app.route('/api/ctupload', methods=['POST'])
@login_required
@cross_origin()
def CTUpload():
    response_object = {'status': 'success'}
    file = request.files['file']
    uploadname = secure_filename(file.filename)
    id = request.form['id']
    img_type = request.form['type']
    cttime = request.form['date1'][:10]
    filename = img_type + "_" + uuid.uuid4().hex + ".nii.gz"
    save_path = app.config['UPLOAD_FOLDER']
    os.makedirs(save_path, exist_ok=True)
    save_file = os.path.join(save_path, filename)
    if not add_item(id, img_type, filename, uploadname, cttime):
        response_object['status'] = 'fail'
    else:
        file.save(save_file)
    return jsonify(response_object)


# model_svr
@app.route('/api/getDetail', methods=['POST'])
@login_required
@cross_origin()
def getDetail():
    response_object = {'status': 'success'}
    json = request.get_json()
    id = json['id']
    patient = _getPatient(id)
    if patient:
        response_object['patient'] = patient
    else:
        response_object['status'] = "fail"
        return jsonify(response_object)
    img_list = _get_img_list(id)
    response_object['imgs'] = img_list
    return jsonify(response_object)


# model_svr
def _getResults(id):
    def to_dict(p):
        results = p.results.order_by(Result.time).all()[::-1]
        res = []
        for r in results:
            timeArray = time.localtime(float(r.time))
            stime = time.strftime('%Y-%m-%d %H:%M:%S', timeArray)
            res.append({'id': r.id, 'time': stime, 'name1': r.filename1,
                        'name2': r.filename2,
                        'modelType': "Random Forest" if r.modelType == 0 else "Random Forest+U-Net",
                        "p_name": p.username})

        return res

    patient = Patient.query.filter_by(id=id).first()
    doctor = _get_current_user()
    if doctor.userType == 1 or patient.docter == doctor:
        return to_dict(patient)
    else:
        return None


# model_svr
@app.route('/api/getResults', methods=['POST'])
@login_required
@cross_origin()
def getResults():
    response_object = {'status': 'success'}
    json = request.get_json()
    id = json['id']
    patient = _getResults(id)
    if patient:
        response_object['results'] = patient
    else:
        response_object['status'] = "fail"
    return jsonify(response_object)


# model_svr
def _getInpOut(id):
    result = Result.query.filter_by(id=id).first()
    if not result:
        return None, None, None, None, None
    adc_file = result.adc_name
    dwi_file = result.dwi_name
    res_file1 = result.filename1
    res_file2 = result.filename2
    info = result.info
    return adc_file, dwi_file, res_file1, res_file2, info


# model_svr
@app.route('/api/getInpOut', methods=['POST'])
@login_required
@cross_origin()
def getInpOut():
    response_object = {'status': 'success'}
    json = request.get_json()
    id = json['id']
    adc_file, dwi_file, res_file1, res_file2, info = _getInpOut(id)
    if adc_file or dwi_file or res_file1 or res_file2:
        if dwi_file:
            response_object['dwi_file'] = dwi_file
            dwi_file = os.path.join(app.config['UPLOAD_FOLDER'], dwi_file)
            response_object['dwi_imgs'], response_object['dwi_slices'] = getAllSlice(dwi_file)
        if adc_file:
            response_object['adc_file'] = adc_file
            adc_file = os.path.join(app.config['UPLOAD_FOLDER'], adc_file)
            response_object['adc_imgs'], response_object['adc_slices'] = getAllSlice(adc_file)
        if res_file1:
            response_object['res_file1'] = res_file1
            res_file1 = os.path.join(app.config['RESULT_FOLDER'], res_file1)
            response_object['res_imgs1'], response_object['res_slices1'] = getAllSlice(res_file1, thres=0.25)
        if res_file2:
            response_object['res_file2'] = res_file2
            res_file2 = os.path.join(app.config['RESULT_FOLDER'], res_file2)
            response_object['res_imgs2'], response_object['res_slices2'] = getAllSlice(res_file2, thres=0.25)
        if info:
            info = round(info, 2)
            response_object['info'] = info
    else:
        response_object['status'] = "fail"
    return jsonify(response_object)


# model_svr
def getAllSlice(filename, thres=None):
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


# model_svr
@app.route('/api/ctimg', methods=['POST'])
@login_required
@cross_origin()
def getImage():
    response_object = {'status': 'success'}
    dwi_file = request.get_json()['dwi']
    adc_file = request.get_json()['adc']

    if dwi_file:
        dwi_file = os.path.join(app.config['UPLOAD_FOLDER'], dwi_file)
        response_object['dwi_imgs'], response_object['dwi_slices'] = getAllSlice(dwi_file)
    if adc_file:
        adc_file = os.path.join(app.config['UPLOAD_FOLDER'], adc_file)
        response_object['adc_imgs'], response_object['adc_slices'] = getAllSlice(adc_file)

    return jsonify(response_object)


# model_svr
def _get_img_list(id):
    res = []
    img_list = Patient.query.filter_by(id=id).first().ctimgs.order_by("time").all()
    for item in img_list:
        res.append(
            {
                "uploadname": item.uploadname,
                "time": time.strftime("%Y%m%d", time.localtime(int(item.time))),
                "type": item.type,
                "filename": item.filename,
                "disabled": False
            }
        )
    return res


# model_svr
@app.route('/api/imgList', methods=['POST'])
@login_required
@cross_origin()
def getImgList():
    response_object = {'status': 'success'}
    patient = request.get_json()['patient']
    if not patient:
        return response_object
    img_list = _get_img_list(patient)
    response_object['imgs'] = img_list
    return jsonify(response_object)


# model_svr
def _delImage(filename):
    ctimg = CTImg.query.filter_by(filename=filename).first()
    if ctimg:
        db.session.delete(ctimg)
        db.session.commit()
        os.remove(filename)
        return "delete success"
    return "not exist"


# model_svr
@app.route('/api/delImage', methods=['POST'])
@login_required
@cross_origin()
def delImage():
    response_object = {
        'status': 'success',
        'dwi': 'fail',
        'adc': 'fail',
    }
    dwi_file = request.get_json()['dwi_file']
    adc_file = request.get_json()['adc_file']
    if dwi_file:
        _delImage(dwi_file)
        response_object['dwi'] = 'success'
    if adc_file:
        _delImage(adc_file)
        response_object['adc'] = 'success'
    return jsonify(response_object)


# model_svr
@app.route('/api/getModel', methods=['GET'])
@login_required
@cross_origin()
def getModel():
    response_object = {'status': 'success'}
    doctor = _get_current_user()
    if not doctor:
        response_object['status'] = 'fail'
    response_object['model'] = doctor.modelType
    return jsonify(response_object)


# model_svr
@app.route('/api/selectModel', methods=['POST'])
@login_required
@cross_origin()
def selectModel():
    response_object = {'status': 'success'}
    model = request.get_json()['model']
    doctor = _get_current_user()
    if not doctor:
        response_object['status'] = 'fail'
    doctor.modelType = model
    db.session.commit()
    return jsonify(response_object)


# model_svr
@app.route('/api/analyze', methods=['POST'])
@login_required
@cross_origin()
def analyze():
    def base64(imgs):
        res = []
        for idx in range(imgs.shape[2]):
            res.append(img_to_base64(imgs[:, :, idx]))
        return res, str(imgs.shape[2])

    response_object = {'status': 'success'}
    json = request.get_json()
    modelType = int(json['backmodel'])
    dwi_name = json['dwi']
    adc_name = json['adc']
    id = json['id']
    if dwi_name or adc_name:
        if dwi_name:
            dwi_file = os.path.join(app.config['UPLOAD_FOLDER'], dwi_name)
        if adc_name:
            adc_file = os.path.join(app.config['UPLOAD_FOLDER'], adc_name)
    else:
        response_object['status'] = 'fail'
        return jsonify(response_object)
    imgs = load_imgs(adc_file, dwi_file)
    dwi_arr = imgs.get('dwi')
    adc_arr = imgs.get('adc')
    affine = imgs.get('affine')
    if modelType == 0:
        perf_preds, nonperf_preds, info = stage2(perf_model, nonperf_model, perf_clf, nonperf_clf, dwi_arr, adc_arr,
                                                 socketio)
    else:
        perf_preds, nonperf_preds, info = stage1_2(perf_model, nonperf_model, perf_clf, nonperf_clf, dwi_arr, adc_arr,
                                                   socketio)
        # perf_preds, nonperf_preds, info = stage1_2(sess, X, perf_pred, perf_clf, nonperf_clf, dwi_arr, adc_arr,
        #                                            socketio)
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
    return jsonify(response_object)


# model_svr
@app.route("/api/download1/<path:filename>", methods=['GET'])
@login_required
@cross_origin()
def download_file1(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# model_svr
@app.route("/api/download2/<path:filename>", methods=['GET'])
@login_required
@cross_origin()
def download_file2(filename):
    return send_from_directory(app.config['RESULT_FOLDER'], filename)


# model_svr
def _delResult(id):
    res = Result.query.filter_by(id=id).first()
    if not res:
        return False
    db.session.delete(res)
    os.remove(os.path.join(app.config['RESULT_FOLDER'], res.filename1))
    os.remove(os.path.join(app.config['RESULT_FOLDER'], res.filename2))
    db.session.commit()
    return True


# model_svr
@app.route('/api/delResult', methods=['POST'])
@login_required
@cross_origin()
def delResult():
    response_object = {'status': 'success'}
    id = request.get_json()['resid']
    if not _delResult(id):
        response_object['status'] = 'fail'
    return jsonify(response_object)


# model_svr
@app.route('/api/ROI', methods=['POST'])
@login_required
@cross_origin()
def ROIUpload():
    response_object = {'status': 'success'}
    file = request.files['file']
    uploadname = secure_filename(file.filename)
    id = request.form['id']
    filename = uuid.uuid4().hex + '_' + uploadname
    save_path = app.config['UPLOAD_FOLDER']
    os.makedirs(save_path, exist_ok=True)
    save_file = os.path.join(save_path, filename)
    r = Result.query.filter_by(id=id).first()
    if not r:
        response_object['status'] = 'fail'
    else:
        if r.roi:
            os.remove(os.path.join(save_path, r.roi))
        r.roi = filename
        db.session.commit()
        file.save(save_file)
    return jsonify(response_object)


# model_svr
@app.route('/api/realimg', methods=['POST'])
@login_required
@cross_origin()
def realimgUpload():
    response_object = {'status': 'success'}
    file = request.files['file']
    uploadname = secure_filename(file.filename)
    id = request.form['id']
    filename = uuid.uuid4().hex + '_' + uploadname
    save_path = app.config['UPLOAD_FOLDER']
    os.makedirs(save_path, exist_ok=True)
    save_file = os.path.join(save_path, filename)
    r = Result.query.filter_by(id=id).first()
    if not r:
        response_object['status'] = 'fail'
    else:
        if r.realimg:
            os.remove(os.path.join(save_path, r.realimg))
        r.realimg = filename
        db.session.commit()
        file.save(save_file)
    return jsonify(response_object)


# model_svr
def _getInpAndFix(id):
    result = Result.query.filter_by(id=id).first()
    if not result:
        return None, None, None, None
    adc_file = result.adc_name
    dwi_file = result.dwi_name
    realimg = result.realimg
    roi = result.roi
    return adc_file, dwi_file, realimg, roi


# model_svr
@app.route('/api/getInp', methods=['POST'])
@login_required
@cross_origin()
def getInpAndFix():
    response_object = {'status': 'success'}
    json = request.get_json()
    id = json['id']
    adc_file, dwi_file, realimg, roi = _getInpAndFix(id)
    if adc_file or dwi_file or realimg or roi:
        if dwi_file:
            response_object['dwi_file'] = dwi_file
            dwi_file = os.path.join(app.config['UPLOAD_FOLDER'], dwi_file)
            response_object['dwi_imgs'], response_object['dwi_slices'] = getAllSlice(dwi_file)
        if adc_file:
            response_object['adc_file'] = adc_file
            adc_file = os.path.join(app.config['UPLOAD_FOLDER'], adc_file)
            response_object['adc_imgs'], response_object['adc_slices'] = getAllSlice(adc_file)
        if realimg:
            response_object['realimg'] = realimg
        if roi:
            response_object['roi'] = roi

    else:
        response_object['status'] = "fail"
    return jsonify(response_object)


# model_svr
def _getFixList():
    doctor = _get_current_user()
    if doctor.userType == 1:
        results = Result.query.all()
        res = []
        for r in results:
            if r.realimg and r.roi:
                res.append({"id": r.id, "d_name": r.docter.username, "p_name": r.patient.username,
                            "modelType": "Random Forest" if r.modelType == 0 else "Random Forest+U-Net"
                            })
        return res

    else:
        return "not allowed"


# model_svr
@app.route('/api/getfixlist', methods=['GET'])
@login_required
@cross_origin()
def getFixList():
    response_object = {'status': 'success'}
    res = _getFixList()
    if res == "not allowed":
        response_object['status'] = "not allowed"
    elif res:
        response_object['res'] = res
    else:
        response_object['status'] = 'fail'
    return jsonify(response_object)


# model_svr
def _delFix(id):
    res = Result.query.filter_by(id=id).first()
    if not res:
        return False
    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], res.realimg))
    os.remove(os.path.join(app.config['UPLOAD_FOLDER'], res.roi))
    res.realimg = None
    res.roi = None
    db.session.commit()
    return True


# model_svr
@app.route('/api/delFix', methods=['POST'])
@login_required
@cross_origin()
def delFix():
    response_object = {'status': 'success'}
    id = request.get_json()['resid']
    if not _delFix(id):
        response_object['status'] = 'fail'
    return jsonify(response_object)


# model_svr
def _eval(gt, pred, dwi):
    idx = np.where(dwi.flatten() > 1000)
    preds = pred.flatten()[idx]
    gts = gt.flatten()[idx]
    tn, fp, fn, tp = metrics.confusion_matrix(gts, preds > 0.15).ravel()
    sensitivity = tp / (tp + fn)
    specifity = tn / (fp + tn)
    auc = metrics.roc_auc_score(gts, preds)
    accuracy = metrics.accuracy_score(gts, preds > 0.15)
    return accuracy, specifity, sensitivity, auc


# model_svr
@app.route('/api/eval', methods=['POST'])
@login_required
@cross_origin()
def eval():
    response_object = {'status': 'success'}
    id = request.get_json()['resid']
    dataset = request.get_json()['dataset']
    res = Result.query.filter_by(id=id).first()
    if not res:
        response_object['status'] = 'fail'
        return jsonify(response_object)
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
    return jsonify(response_object)


if __name__ == '__main__':
    def after_request(resp):
        # resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Credentials'] = 'true'
        return resp


    perf_model, nonperf_model = stage1_init()
    perf_clf, nonperf_clf = stage2_init()
    app.after_request(after_request)
    socketio.run(app, host='0.0.0.0', port=5051)
